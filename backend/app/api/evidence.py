"""
Evidence viewer endpoints.

Expose the real stored page text and chunk text so every citation in the app
can be opened and inspected. Page/chunk lookups are scoped to owned
documents, and page numbers that don't exist return 404 (never invented).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.api.auth import get_current_user
from app.api.upload import _get_owned_document

router = APIRouter(prefix="/api/documents", tags=["evidence"])


@router.get("/{document_id}/pages", response_model=list[schemas.DocumentPageOut])
def list_pages(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    pages = (
        db.query(models.DocumentPage)
        .filter(models.DocumentPage.document_id == doc.id)
        .order_by(models.DocumentPage.page_number)
        .all()
    )
    return [
        schemas.DocumentPageOut(page_number=p.page_number, text=p.text, ocr_used=p.ocr_used)
        for p in pages
    ]


@router.get("/{document_id}/pages/{page_number}", response_model=schemas.DocumentPageOut)
def get_page(document_id: str, page_number: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    page = (
        db.query(models.DocumentPage)
        .filter(models.DocumentPage.document_id == doc.id, models.DocumentPage.page_number == page_number)
        .first()
    )
    if not page:
        raise HTTPException(status_code=404, detail=f"Page {page_number} does not exist for this document.")
    return schemas.DocumentPageOut(page_number=page.page_number, text=page.text, ocr_used=page.ocr_used)


@router.get("/{document_id}/chunks/{chunk_id}", response_model=schemas.ChunkOut)
def get_chunk(document_id: str, chunk_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    chunk = (
        db.query(models.DocumentChunk)
        .filter(models.DocumentChunk.id == chunk_id, models.DocumentChunk.document_id == doc.id)
        .first()
    )
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found in this document.")
    return chunk
