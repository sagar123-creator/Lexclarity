"""
Orchestrates the full document-processing pipeline:

Upload -> Extract (with OCR fallback) -> Persist page text -> Clean -> Split
-> Chunk -> Embed -> Store in vector DB -> Summarize -> Extract
clauses/risks/obligations/dates/entities (each quote-validated) -> Normalize
dates -> Run missing-clause checklist -> Create action items -> Ready

Each stage updates `document.status` so the frontend can poll and show
progress, and any failure is captured on `document.error_message` instead of
crashing silently. Re-running the pipeline replaces previously derived
analysis rows (but never the uploaded original, and never action items the
user has already decided on). A resume (`resume_missing=True`) is the
exception: it keeps every section that already produced results and only
re-runs the ones that came back empty.
"""
from sqlalchemy.orm import Session

from app import models
from app.services import document_parser, chunking, embeddings, vector_store
from app.services import summarizer, risk_analyzer, extractor, missing_clauses, action_center
from app.services import cancellation
from app.services.dates import normalize_date_expression, find_anchor_date
from app.services.llm import LLMError


class PipelineStopped(Exception):
    """Raised at a stage boundary once the user asked to stop processing.

    Caught inside :func:`process_document`, which settles the document as
    ``stopped`` (keeping whatever the completed stages already wrote) instead
    of failing it.
    """


def process_document(
    db: Session, document: models.Document, *, resume_missing: bool = False
) -> None:
    """Run the analysis pipeline for one document.

    ``resume_missing`` retries only the stages that produced nothing, keeping
    every section that already succeeded (see ``_completed_stages``). Uploads
    and callers that want a fresh derivation leave it ``False``.

    The run is cancellable: a stop request made through
    ``app.services.cancellation`` is honoured at the next stage boundary, the
    document is settled as ``stopped``, and everything written before that
    boundary is kept (so a later resume picks up where it left off).
    """
    cancellation.mark_running(document.id)
    try:
        document.error_message = None
        db.commit()
        _set_status(db, document, "extracting")
        pages = document_parser.extract_text(document.storage_path, document.file_type)
        document.page_count = len(pages)
        ocr_pages = {p.page_number for p in pages if p.ocr_used}
        document.ocr_used = bool(ocr_pages)
        if not ocr_pages:
            document.extraction_method = "text"
        elif len(ocr_pages) == len(pages):
            document.extraction_method = "ocr"
        else:
            document.extraction_method = "mixed"
        db.commit()

        # Persist page text — the source of truth for the evidence viewer.
        db.query(models.DocumentPage).filter(
            models.DocumentPage.document_id == document.id
        ).delete(synchronize_session=False)
        for p in pages:
            db.add(models.DocumentPage(
                document_id=document.id,
                page_number=p.page_number,
                text=p.text,
                ocr_used=p.ocr_used,
            ))
        db.commit()

        have = _completed_stages(db, document)
        # Chunk rows are only reusable on a resume, and only if they survived:
        # without them the derived rows we would keep could not keep their
        # evidence links (`source_chunk_id`), so those cases rebuild instead.
        prior_chunks = (
            db.query(models.DocumentChunk)
            .filter(models.DocumentChunk.document_id == document.id)
            .order_by(models.DocumentChunk.chunk_index)
            .all()
        )
        # Resume = retry of a partially-failed run: keep every section that
        # already produced results and re-run only the empty ones. That is what
        # the partial-failure message promises ("Re-analyze the document to
        # retry those sections") and, while the provider's per-day quota is
        # scarce, it is the difference between a retry that reaches the empty
        # sections and one that burns the budget re-doing the ones that work.
        # Nothing missing (or everything missing) has no resume semantics —
        # both rebuild from scratch.
        resuming = (
            resume_missing
            and any(have.values())
            and not all(have.values())
            and bool(prior_chunks)
        )

        if resuming:
            # Drop only the rows that are about to be re-derived, so the
            # sections we keep stay intact (chunk evidence links included).
            _clear_stages(db, document, [name for name, ok in have.items() if not ok])
            chunk_rows = prior_chunks
            if any(not r.embedded for r in chunk_rows):
                # Embedding never finished last time — redo it, keeping IDs.
                _set_status(db, document, "embedding")
                _embed_chunks(db, document, chunk_rows)
        else:
            # Replace previous derived rows on re-analysis (keep decided actions).
            _clear_derived(db, document)

            _set_status(db, document, "chunking")
            chunks = chunking.chunk_pages(pages)
            if not chunks:
                raise ValueError("No usable text could be extracted from this document.")

            chunk_rows = []
            for c in chunks:
                row = models.DocumentChunk(
                    document_id=document.id,
                    chunk_index=c.chunk_index,
                    page_number=c.page_number,
                    section_heading=c.section_heading,
                    text=c.text,
                    token_count=c.token_count,
                )
                db.add(row)
                chunk_rows.append(row)
            db.commit()
            for row in chunk_rows:
                db.refresh(row)

            _set_status(db, document, "embedding")
            _embed_chunks(db, document, chunk_rows)

        _set_status(db, document, "analyzing")
        all_chunks_dicts = [{"chunk_id": r.id, "text": r.text, "page_number": r.page_number} for r in chunk_rows]

        def _kept(stage: str) -> bool:
            """Resume mode is preserving this stage's earlier result."""
            return resuming and have[stage]

        # Each core LLM stage can fail independently (provider outage, daily
        # quota exhaustion, malformed output). We track failures with their
        # exact reason instead of crashing on the first one: if EVERY core
        # stage fails the document is marked failed with an actionable message;
        # on partial failure the document still completes with the stages that
        # worked plus a note listing exactly what is missing and why.
        stage_failures: list[str] = []
        # Once a stage fails on a per-DAILY-quota limit, no later LLM stage can
        # succeed until the window resets — so we skip them (recording why)
        # rather than firing calls that would all 429 without spending tokens.
        quota_exhausted = False

        def _note_failure(stage: str, err: LLMError) -> None:
            nonlocal quota_exhausted
            stage_failures.append(f"{stage}: {err}")
            if getattr(err, "rate_limit_kind", None) == "daily":
                quota_exhausted = True

        def _skip_if_quota(stage: str) -> bool:
            if quota_exhausted:
                stage_failures.append(f"{stage}: skipped — the LLM daily quota is exhausted.")
                return True
            return False

        def _abort_if_stopped() -> None:
            """Honour a stop request at a stage boundary.

            A stage already in flight finishes (tearing an LLM call out
            mid-request would waste the tokens anyway); everything the earlier
            stages committed is kept for the next resume.
            """
            if cancellation.stop_requested(document.id):
                raise PipelineStopped()

        summary = {}
        _abort_if_stopped()
        if not _kept("summary"):
            try:
                summary = summarizer.summarize_document(document.id, all_chunks_dicts)
                if summary.get("error"):
                    stage_failures.append(f"Summary: {summary['error']}")
            except LLMError as e:
                _note_failure("Summary", e)
                summary = {}
            analysis = db.query(models.DocumentAnalysis).filter(
                models.DocumentAnalysis.document_id == document.id
            ).first()
            if analysis is None:
                analysis = models.DocumentAnalysis(document_id=document.id)
                db.add(analysis)
            analysis.executive_summary = summary.get("executive_summary")
            analysis.document_type = summary.get("document_type")
            analysis.plain_english_overview = summary.get("plain_english_overview")
            document.document_type = summary.get("document_type")
            db.commit()

        entities = []
        _abort_if_stopped()
        if not _kept("entities"):
            if not _skip_if_quota("Entities"):
                try:
                    entities = extractor.extract_entities(document.id) or []
                except LLMError as e:
                    _note_failure("Entities", e)
            for e in entities:
                if not isinstance(e, dict):
                    continue
                db.add(models.Entity(
                    document_id=document.id,
                    name=e.get("name", "Unknown"),
                    role=e.get("role"),
                    entity_type=e.get("entity_type"),
                ))
            db.commit()

        obligations = []
        _abort_if_stopped()
        if not _kept("obligations"):
            if not _skip_if_quota("Obligations"):
                try:
                    obligations = extractor.extract_obligations(db, document.id) or []
                except LLMError as e:
                    _note_failure("Obligations", e)
            for o in obligations:
                db.add(models.Obligation(
                    document_id=document.id,
                    party_name=o.get("party_name", "Unknown"),
                    obligation_text=o.get("obligation_text", ""),
                    page_number=o.get("page_number"),
                    section_reference=o.get("section"),
                    source_chunk_id=o.get("chunk_id"),
                    deadline_text=o.get("deadline_text"),
                    trigger_event=o.get("trigger_event"),
                    conditions=o.get("conditions"),
                    evidence_quote=o.get("quote"),
                    verification_status=o.get("verification_status"),
                    task_status="pending",
                ))
            db.commit()

        date_items = []
        _abort_if_stopped()
        if not _kept("dates"):
            if not _skip_if_quota("Dates"):
                try:
                    date_items = extractor.extract_dates(db, document.id) or []
                except LLMError as e:
                    _note_failure("Dates", e)
            anchor = find_anchor_date(date_items)
            for d in date_items:
                norm = normalize_date_expression(d.get("date_value"), anchor_date=anchor)
                db.add(models.ImportantDate(
                    document_id=document.id,
                    label=d.get("label", "Date"),
                    date_value=d.get("date_value"),
                    description=d.get("description"),
                    page_number=d.get("page_number"),
                    source_chunk_id=d.get("chunk_id"),
                    normalized_date=norm["normalized_date"],
                    date_kind=norm["date_kind"],
                    extraction_status=norm["extraction_status"],
                    evidence_quote=d.get("quote"),
                    verification_status=d.get("verification_status"),
                ))
            db.commit()

        clauses = []
        _abort_if_stopped()
        if not _kept("clauses"):
            if not _skip_if_quota("Clauses"):
                try:
                    clauses = extractor.extract_clauses(db, document.id) or []
                except LLMError as e:
                    _note_failure("Clauses", e)
            for c in clauses:
                db.add(models.Clause(
                    document_id=document.id,
                    category=c.get("category", "Other"),
                    title=c.get("title", c.get("category", "Clause")),
                    original_text=c.get("original_text"),
                    plain_explanation=c.get("plain_explanation"),
                    page_number=c.get("page_number"),
                    section_reference=c.get("section"),
                    source_chunk_id=c.get("chunk_id"),
                    parties=c.get("parties") if isinstance(c.get("parties"), list) else None,
                    rights_obligations=c.get("rights_obligations"),
                    concerns=c.get("concerns"),
                    evidence_quote=c.get("original_text"),
                    char_start=c.get("char_start"),
                    char_end=c.get("char_end"),
                    verification_status=c.get("verification_status"),
                ))
            db.commit()

        risks = []
        _abort_if_stopped()
        if not _kept("risks"):
            if not _skip_if_quota("Risks"):
                try:
                    risks = risk_analyzer.analyze_risks(db, document.id, ocr_pages=ocr_pages) or []
                except LLMError as e:
                    _note_failure("Risks", e)
            for r in risks:
                db.add(models.Risk(
                    document_id=document.id,
                    level=r.get("level", "Low"),
                    title=r.get("title", "Potential risk"),
                    description=r.get("description", ""),
                    why_it_matters=r.get("why_it_matters", ""),
                    plain_explanation=r.get("plain_explanation"),
                    page_number=r.get("page_number"),
                    section_reference=r.get("section"),
                    source_chunk_id=r.get("chunk_id"),
                    category=r.get("category"),
                    affected_party=r.get("affected_party"),
                    evidence_quote=r.get("quote"),
                    suggested_action=r.get("suggested_action"),
                    severity_rationale=r.get("severity_rationale"),
                    verification_status=r.get("verification_status"),
                    char_start=r.get("char_start"),
                    char_end=r.get("char_end"),
                ))
            document.overall_risk_level = risk_analyzer.overall_risk_level(risks)
            db.commit()

        # If every core LLM stage failed there is no analysis to show — fail
        # the document with an actionable message rather than a hollow "ready".
        core_stages = 6
        if len(stage_failures) >= core_stages:
            raise LLMError(
                "Analysis could not run: " + " ".join(stage_failures)
                + " Check the LLM provider configuration and try re-analyzing."
            )

        # Missing-clause checklist (preliminary review; best-effort). Skipped
        # when the daily quota is already exhausted — it would only wait on the
        # throttle and 429 again, and its findings are optional. On a resume
        # that kept both of its inputs (document type + clause findings) it is
        # already correct, so it is left alone instead of re-spending quota.
        checklist_kept = (
            _kept("clauses")
            and _kept("summary")
            and db.query(models.ChecklistItem)
            .filter(models.ChecklistItem.document_id == document.id)
            .first()
            is not None
        )
        _abort_if_stopped()
        if not quota_exhausted and not checklist_kept:
            if resuming:
                # Drop the old rows first — a resume must never duplicate the
                # ones kept from the earlier run.
                db.query(models.ChecklistItem).filter(
                    models.ChecklistItem.document_id == document.id
                ).delete(synchronize_session=False)
                db.commit()
            try:
                for item in missing_clauses.run_checklist(document.id, document.document_type):
                    db.add(models.ChecklistItem(
                        document_id=document.id,
                        checklist_type=item["checklist_type"],
                        item_key=item["item_key"],
                        item_label=item["item_label"],
                        state=item["state"],
                        explanation=item["explanation"],
                        evidence_quote=item.get("evidence_quote"),
                        page_number=item.get("page_number"),
                        source_chunk_id=item.get("chunk_id"),
                    ))
                db.commit()
            except Exception:  # noqa: BLE001 - checklist must not fail the pipeline
                db.rollback()

        # Create action items from supported findings (deterministic, idempotent).
        try:
            action_center.generate_action_items(db, document)
        except Exception:  # noqa: BLE001
            db.rollback()

        if stage_failures:
            # Partial outage: the document is still usable, but tell the user
            # exactly which sections are missing rather than silently degrading.
            document.error_message = (
                "Some analysis sections could not be generated: "
                + " ".join(stage_failures)
                + " Re-analyze the document to retry those sections."
            )
        _set_status(db, document, "ready")

    except PipelineStopped:
        db.rollback()
        _stop(db, document)
    except LLMError as e:
        db.rollback()
        _fail(db, document, str(e))
    except Exception as e:  # noqa: BLE001 - surface any pipeline failure to the user
        db.rollback()
        _fail(db, document, str(e))
    finally:
        # The stop flag belongs to this run only: consume it here so it can
        # never leak into a later, deliberately-started analysis.
        cancellation.mark_finished(document.id)
        cancellation.clear_stop(document.id)


# The core LLM stages and the rows each one produces. Resume mode uses this to
# decide which sections already exist and which must be re-run.
_STAGE_TABLES = {
    "entities": models.Entity,
    "obligations": models.Obligation,
    "dates": models.ImportantDate,
    "clauses": models.Clause,
    "risks": models.Risk,
}


def _completed_stages(db: Session, document: models.Document) -> dict[str, bool]:
    """Which core stages already produced results worth keeping on a resume."""
    did = document.id
    analysis = db.query(models.DocumentAnalysis).filter(
        models.DocumentAnalysis.document_id == did
    ).first()
    have = {"summary": bool(analysis and analysis.executive_summary)}
    for name, table in _STAGE_TABLES.items():
        have[name] = (
            db.query(table).filter(table.document_id == did).first() is not None
        )
    return have


def _clear_stages(db: Session, document: models.Document, stages) -> None:
    """Remove only the rows of the stages that are about to re-run.

    Everything else — including the chunk ids their `source_chunk_id` links
    point at — stays untouched, so a retry can keep its earlier sections without
    breaking their evidence links. Undecided action items are derived from
    findings, so they are dropped here and rebuilt by the action centre; ones
    the user already decided on are never touched.
    """
    did = document.id
    for name in stages:
        table = _STAGE_TABLES.get(name)
        if table is not None:
            db.query(table).filter(table.document_id == did).delete(synchronize_session=False)
    db.query(models.ActionItem).filter(
        models.ActionItem.document_id == did,
        models.ActionItem.decision == "undecided",
    ).delete(synchronize_session=False)
    db.commit()


def _embed_chunks(db: Session, document: models.Document, chunk_rows) -> None:
    """Embed the given chunks and upsert them into the vector store."""
    texts = [r.text for r in chunk_rows]
    vectors = embeddings.embed_texts(texts)
    metadatas = [
        {"page_number": r.page_number, "section_heading": r.section_heading or ""}
        for r in chunk_rows
    ]
    store = vector_store.get_vector_store()
    store.upsert_chunks(
        document_id=document.id,
        chunk_ids=[r.id for r in chunk_rows],
        texts=texts,
        embeddings=vectors,
        metadatas=metadatas,
    )
    for r in chunk_rows:
        r.embedded = True
    db.commit()


def _clear_derived(db: Session, document: models.Document) -> None:
    """Remove previously derived analysis so re-analysis doesn't duplicate."""
    did = document.id
    db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id == did).delete(synchronize_session=False)
    db.query(models.Entity).filter(models.Entity.document_id == did).delete(synchronize_session=False)
    db.query(models.Obligation).filter(models.Obligation.document_id == did).delete(synchronize_session=False)
    db.query(models.ImportantDate).filter(models.ImportantDate.document_id == did).delete(synchronize_session=False)
    db.query(models.Clause).filter(models.Clause.document_id == did).delete(synchronize_session=False)
    db.query(models.Risk).filter(models.Risk.document_id == did).delete(synchronize_session=False)
    db.query(models.ChecklistItem).filter(models.ChecklistItem.document_id == did).delete(synchronize_session=False)
    # Undecided action items are regenerated; decided ones are kept as history.
    db.query(models.ActionItem).filter(
        models.ActionItem.document_id == did,
        models.ActionItem.decision == "undecided",
    ).delete(synchronize_session=False)
    db.commit()
    try:
        vector_store.get_vector_store().delete_document(did)
    except Exception:  # noqa: BLE001 - vector cleanup is best-effort
        pass


def _set_status(db: Session, document: models.Document, status: str) -> None:
    # Phase transitions are the pipeline's coarsest stage boundaries (and the
    # first one covers a stop requested while the document was still queued as
    # "uploaded"), so a stop request is checked on every status write.
    if cancellation.stop_requested(document.id):
        raise PipelineStopped()
    document.status = status
    db.commit()


def _stop(db: Session, document: models.Document) -> None:
    """Settle a document whose run was cancelled by the user.

    Deliberately distinct from ``_fail``: stopping is an explicit user action,
    not an error, and the sections written before the stop stay queryable so a
    resume only has to finish what's missing.
    """
    document.status = "stopped"
    document.error_message = cancellation.STOPPED_MESSAGE
    db.commit()


def _fail(db: Session, document: models.Document, message: str) -> None:
    document.status = "failed"
    document.error_message = message
    db.commit()
