"""
Missing-clause checklist API (preliminary document review).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.api.auth import get_current_user
from app.api.upload import _get_owned_document
from app.services import missing_clauses

router = APIRouter(prefix="/api/documents", tags=["checklist"])


@router.get("/{document_id}/checklist", response_model=list[schemas.ChecklistItemOut])
def get_checklist(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    return (
        db.query(models.ChecklistItem)
        .filter(models.ChecklistItem.document_id == doc.id)
        .order_by(models.ChecklistItem.item_key)
        .all()
    )


@router.post("/{document_id}/checklist/run", response_model=list[schemas.ChecklistItemOut])
def run_checklist(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """(Re-)run the missing-clause checklist for this document."""
    doc = _get_owned_document(db, document_id, user)
    if doc.status not in ("ready", "stopped"):
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail=f"Document is still processing (status: {doc.status}).")

    db.query(models.ChecklistItem).filter(
        models.ChecklistItem.document_id == doc.id
    ).delete(synchronize_session=False)
    db.commit()

    for item in missing_clauses.run_checklist(doc.id, doc.document_type):
        db.add(models.ChecklistItem(
            document_id=doc.id,
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
    return get_checklist(document_id, db, user)
