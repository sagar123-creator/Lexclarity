"""
Multi-document case workspace intelligence.

Cross-document retrieval is scoped to exactly the documents in the
workspace, which must all belong to the requesting user — retrieval never
sees other users' documents. Answers attribute every statement to its source
document and explicitly surface conflicts between documents instead of
silently merging them.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services.embeddings import embed_query
from app.services.vector_store import get_vector_store, RetrievedChunk
from app.services.llm import complete_json, LLMError
from app.services.verification import Passage, verify_answer

SYSTEM_PROMPT = """You are LexClarity, answering questions across MULTIPLE legal documents in a case workspace.

Rules:
- Answer ONLY from the provided excerpts. Every excerpt header names its source document.
- Attribute every factual statement to its specific source document (use the document name).
- If two documents state DIFFERENT or CONFLICTING things about the same topic, say so
  explicitly and quote each — never silently merge conflicting statements.
- If the excerpts don't contain the answer, say so rather than guessing.
- Never provide definitive legal advice.

Respond with ONLY a JSON object:
{
  "confidence": "answered" | "not_found" | "low_confidence",
  "answer": "your answer, attributing statements to source documents",
  "citations": [{"document_id": "...", "chunk_id": "...", "page_number": int}],
  "conflicts": [{"topic": str, "document_a": str, "statement_a": str, "document_b": str, "statement_b": str}]
}"""


def workspace_documents(db: Session, workspace: models.Workspace) -> list[models.Document]:
    """Ready documents in the workspace (ownership is enforced by the API
    when the workspace itself is resolved)."""
    ids = [wd.document_id for wd in workspace.documents]
    if not ids:
        return []
    return (
        db.query(models.Document)
        .filter(models.Document.id.in_(ids), models.Document.status == "ready")
        .all()
    )


def search_workspace(db: Session, workspace: models.Workspace, question: str) -> dict:
    """Cross-document RAG over the workspace's documents."""
    docs = workspace_documents(db, workspace)
    doc_ids = [d.id for d in docs]
    if not doc_ids:
        return {
            "answer": "No processed documents in this workspace yet.",
            "citations": [],
            "confidence": "not_found",
            "conflicts": [],
            "verification": {"overall": "insufficient", "claims": []},
        }

    store = get_vector_store()
    query_emb = embed_query(question)
    retrieved = store.query(None, query_emb, top_k=settings.WORKSPACE_RETRIEVAL_TOP_K, document_ids=doc_ids)
    relevant = [r for r in retrieved if r.similarity >= settings.RETRIEVAL_MIN_SIMILARITY]

    if not relevant:
        return {
            "answer": "I couldn't find this information in the workspace documents.",
            "citations": [],
            "confidence": "not_found",
            "conflicts": [],
            "verification": {"overall": "insufficient", "claims": []},
        }

    docs_by_id = {d.id: d for d in docs}
    chunk_rows = {
        c.id: c
        for c in db.query(models.DocumentChunk)
        .filter(models.DocumentChunk.id.in_([r.chunk_id for r in relevant]))
        .all()
    }

    context_blocks = []
    for r in relevant:
        row = chunk_rows.get(r.chunk_id)
        doc = docs_by_id.get(row.document_id) if row else None
        doc_name = doc.filename if doc else "unknown document"
        doc_id = row.document_id if row else "unknown"
        context_blocks.append(
            f"[document={doc_name} document_id={doc_id} "
            f"chunk_id={r.chunk_id} page={r.page_number} section={r.section_heading or 'n/a'}]\n{r.text}"
        )
    context = "\n\n".join(context_blocks)

    prompt = f"""Workspace documents: {", ".join(d.filename for d in docs)}

Relevant excerpts (each tagged with its source document):
{context}

Current question: {question}

Answer using only the excerpts. Attribute statements to source documents and report any conflicts."""

    try:
        result = complete_json(SYSTEM_PROMPT, prompt, max_tokens=1400)
    except LLMError as e:
        return {
            "answer": f"I ran into a problem generating an answer: {e}",
            "citations": [],
            "confidence": "low_confidence",
            "conflicts": [],
            "verification": {"overall": "insufficient", "claims": []},
        }

    if not isinstance(result, dict):
        return {
            "answer": "I couldn't generate a reliable answer from these documents. Please try rephrasing.",
            "citations": [],
            "confidence": "low_confidence",
            "conflicts": [],
            "verification": {"overall": "insufficient", "claims": []},
        }

    by_id = {r.chunk_id: r for r in relevant}
    enriched = []
    for c in (result.get("citations") or []):
        if not isinstance(c, dict):
            continue
        chunk = by_id.get(c.get("chunk_id"))
        row = chunk_rows.get(c.get("chunk_id"))
        doc = docs_by_id.get(row.document_id) if row else None
        if chunk is None or doc is None:
            continue  # never surface unverifiable references
        enriched.append({
            "document_id": doc.id,
            "document_name": doc.filename,
            "chunk_id": chunk.chunk_id,
            "page_number": chunk.page_number,
            "section_reference": chunk.section_heading,
            "snippet": chunk.text[:220] + ("…" if len(chunk.text) > 220 else ""),
            "verified": True,
        })

    answer_text = str(result.get("answer") or "").strip()
    conflicts = [c for c in (result.get("conflicts") or []) if isinstance(c, dict)]

    passages = []
    for r in relevant:
        row = chunk_rows.get(r.chunk_id)
        ocr = bool(row and row.document_id in {d.id for d in docs if d.ocr_used})
        passages.append(Passage(
            text=r.text, similarity=r.similarity, chunk_id=r.chunk_id,
            page_number=r.page_number, section_heading=r.section_heading, ocr_used=ocr,
        ))
    verification = verify_answer(answer_text, passages)

    confidence = str(result.get("confidence") or "answered")
    if verification["overall"] == "contradicted" and confidence == "answered":
        confidence = "low_confidence"

    return {
        "answer": answer_text,
        "citations": enriched,
        "confidence": confidence,
        "conflicts": conflicts,
        "verification": verification,
    }


def cross_document_timeline(db: Session, workspace: models.Workspace) -> list[dict]:
    """Merged timeline of important dates across the workspace's documents."""
    docs = workspace_documents(db, workspace)
    doc_ids = [d.id for d in docs]
    if not doc_ids:
        return []
    dates = (
        db.query(models.ImportantDate)
        .filter(models.ImportantDate.document_id.in_(doc_ids))
        .all()
    )
    docs_by_id = {d.id: d for d in docs}
    out = []
    for d in dates:
        doc = docs_by_id.get(d.document_id)
        out.append({
            "date_id": d.id,
            "document_id": d.document_id,
            "document_name": doc.filename if doc else None,
            "label": d.label,
            "date_value": d.date_value,
            "normalized_date": d.normalized_date,
            "date_kind": d.date_kind,
            "extraction_status": d.extraction_status,
            "page_number": d.page_number,
        })
    out.sort(key=lambda x: (x["normalized_date"] or "9999-99-99"))
    return out


def cross_document_obligations(db: Session, workspace: models.Workspace) -> list[dict]:
    """Per-document obligations with source attribution."""
    docs = workspace_documents(db, workspace)
    doc_ids = [d.id for d in docs]
    if not doc_ids:
        return []
    obligations = (
        db.query(models.Obligation)
        .filter(models.Obligation.document_id.in_(doc_ids))
        .all()
    )
    docs_by_id = {d.id: d for d in docs}
    return [{
        "obligation_id": o.id,
        "document_id": o.document_id,
        "document_name": (docs_by_id.get(o.document_id).filename if o.document_id in docs_by_id else None),
        "party_name": o.party_name,
        "obligation_text": o.obligation_text,
        "deadline_text": o.deadline_text,
        "trigger_event": o.trigger_event,
        "page_number": o.page_number,
        "verification_status": o.verification_status,
    } for o in obligations]
