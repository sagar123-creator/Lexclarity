"""
Orchestrates the full document-processing pipeline described in the product
spec:

Upload -> Extract -> Clean -> Split -> Chunk -> Embed -> Store in vector DB
-> Summarize -> Extract clauses/risks/obligations/dates/entities -> Ready

Each stage updates `document.status` so the frontend can poll and show
progress, and any failure is captured on `document.error_message` instead of
crashing silently.
"""
from sqlalchemy.orm import Session

from app import models
from app.services import document_parser, chunking, embeddings, vector_store
from app.services import summarizer, risk_analyzer, extractor
from app.services.llm import LLMError


def process_document(db: Session, document: models.Document) -> None:
    try:
        document.error_message = None
        db.commit()
        _set_status(db, document, "extracting")
        pages = document_parser.extract_text(document.storage_path, document.file_type)
        document.page_count = len(pages)

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

        _set_status(db, document, "analyzing")
        all_chunks_dicts = [{"chunk_id": r.id, "text": r.text, "page_number": r.page_number} for r in chunk_rows]

        summary = summarizer.summarize_document(document.id, all_chunks_dicts)
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

        for e in extractor.extract_entities(document.id):
            db.add(models.Entity(
                document_id=document.id,
                name=e.get("name", "Unknown"),
                role=e.get("role"),
                entity_type=e.get("entity_type"),
            ))

        for o in extractor.extract_obligations(document.id):
            db.add(models.Obligation(
                document_id=document.id,
                party_name=o.get("party_name", "Unknown"),
                obligation_text=o.get("obligation_text", ""),
                page_number=o.get("page_number"),
                source_chunk_id=o.get("chunk_id"),
            ))

        for d in extractor.extract_dates(document.id):
            db.add(models.ImportantDate(
                document_id=document.id,
                label=d.get("label", "Date"),
                date_value=d.get("date_value"),
                description=d.get("description"),
                page_number=d.get("page_number"),
                source_chunk_id=d.get("chunk_id"),
            ))

        for c in extractor.extract_clauses(document.id):
            db.add(models.Clause(
                document_id=document.id,
                category=c.get("category", "Other"),
                title=c.get("title", c.get("category", "Clause")),
                original_text=c.get("original_text"),
                plain_explanation=c.get("plain_explanation"),
                page_number=c.get("page_number"),
                source_chunk_id=c.get("chunk_id"),
            ))

        risks = risk_analyzer.analyze_risks(document.id)
        for r in risks:
            db.add(models.Risk(
                document_id=document.id,
                level=r.get("level", "Low"),
                title=r.get("title", "Potential risk"),
                description=r.get("description", ""),
                why_it_matters=r.get("why_it_matters", ""),
                plain_explanation=r.get("plain_explanation"),
                page_number=r.get("page_number"),
                source_chunk_id=r.get("chunk_id"),
            ))
        document.overall_risk_level = risk_analyzer.overall_risk_level(risks)

        db.commit()
        _set_status(db, document, "ready")

    except LLMError as e:
        db.rollback()
        _fail(db, document, str(e))
    except Exception as e:  # noqa: BLE001 - surface any pipeline failure to the user
        db.rollback()
        _fail(db, document, str(e))


def _set_status(db: Session, document: models.Document, status: str) -> None:
    document.status = status
    db.commit()


def _fail(db: Session, document: models.Document, message: str) -> None:
    document.status = "failed"
    document.error_message = message
    db.commit()
