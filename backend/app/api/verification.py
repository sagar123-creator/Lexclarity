"""
On-demand claim verification endpoint (Advanced Analysis).

Lets the UI verify an arbitrary claim against a document (optionally scoped
to one cited chunk), using the same Trust & Verification engine that runs
during the pipeline and chat.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.api.auth import get_current_user
from app.api.upload import _get_owned_document
from app.services.verification import Passage, verify_claim
from app.services.evidence import get_chunk

router = APIRouter(prefix="/api/documents", tags=["verification"])


@router.post("/{document_id}/verify-claim", response_model=schemas.VerifyClaimResponse)
def verify_claim_endpoint(
    document_id: str,
    body: schemas.VerifyClaimRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    doc = _get_owned_document(db, document_id, user)
    if doc.status not in ("ready", "stopped"):
        raise HTTPException(status_code=409, detail=f"Document is still processing (status: {doc.status}).")

    ocr_pages = {p.page_number for p in db.query(models.DocumentPage).filter(
        models.DocumentPage.document_id == doc.id, models.DocumentPage.ocr_used == True  # noqa: E712
    ).all()}

    if body.chunk_id:
        chunk = get_chunk(db, doc.id, body.chunk_id)
        if not chunk:
            raise HTTPException(status_code=404, detail="Cited chunk not found in this document.")
        passages = [Passage(
            text=chunk.text,
            similarity=1.0,
            chunk_id=chunk.id,
            page_number=chunk.page_number,
            section_heading=chunk.section_heading,
            ocr_used=chunk.page_number in ocr_pages,
        )]
    else:
        # Verify against the document's most relevant passages.
        from app.services.embeddings import embed_query
        from app.services.vector_store import get_vector_store
        from app.config import settings

        store = get_vector_store()
        retrieved = store.query(doc.id, embed_query(body.claim), top_k=settings.RETRIEVAL_TOP_K)
        passages = [Passage(
            text=r.text,
            similarity=r.similarity,
            chunk_id=r.chunk_id,
            page_number=r.page_number,
            section_heading=r.section_heading,
            ocr_used=r.page_number in ocr_pages,
        ) for r in retrieved]

    result = verify_claim(body.claim, passages)

    # Persist the verification record for auditability.
    db.add(models.Verification(
        document_id=doc.id,
        subject_type="claim",
        subject_id=body.chunk_id,
        claim_text=body.claim,
        status=result.status,
        method=result.method,
        score=result.score,
        explanation=result.explanation,
        evidence_chunk_ids=[result.evidence_chunk_id] if result.evidence_chunk_id else [],
        evidence_summary=result.evidence_excerpt,
    ))
    db.commit()

    return schemas.VerifyClaimResponse(
        document_id=doc.id,
        result=schemas.ClaimVerificationOut(
            claim=result.claim,
            status=result.status,
            method=result.method,
            explanation=result.explanation,
            score=result.score,
            evidence_chunk_id=result.evidence_chunk_id,
            evidence_page=result.evidence_page,
            evidence_excerpt=result.evidence_excerpt,
            notes=result.notes,
        ),
    )
