"""
Legal Action Center API.

Action items are generated from the document's findings after analysis.
Users can update status (pending/in_progress/completed) and record a
decision (accept/reject/defer). Decisions are audit-logged. LexClarity never
performs external actions — approval here only records the user's intent.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.api.auth import get_current_user
from app.api.upload import _get_owned_document
from app.services import action_center

router = APIRouter(prefix="/api", tags=["actions"])

VALID_STATUS = {"pending", "in_progress", "completed"}
VALID_DECISION = {"undecided", "accepted", "rejected", "deferred"}


@router.get("/documents/{document_id}/actions", response_model=list[schemas.ActionItemOut])
def list_actions(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    return (
        db.query(models.ActionItem)
        .filter(models.ActionItem.document_id == doc.id)
        .order_by(models.ActionItem.priority.desc(), models.ActionItem.created_at)
        .all()
    )


@router.post("/documents/{document_id}/actions/generate", response_model=list[schemas.ActionItemOut])
def generate_actions(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    if doc.status != "ready":
        raise HTTPException(status_code=409, detail=f"Document is still processing (status: {doc.status}).")
    action_center.generate_action_items(db, doc)
    return list_actions(document_id, db, user)


@router.patch("/actions/{action_id}", response_model=schemas.ActionItemOut)
def update_action(action_id: str, body: schemas.ActionItemUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    action = db.query(models.ActionItem).filter(models.ActionItem.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Action item not found.")
    doc = _get_owned_document(db, action.document_id, user)

    if body.status is not None:
        if body.status not in VALID_STATUS:
            raise HTTPException(status_code=422, detail=f"Invalid status. Use one of: {sorted(VALID_STATUS)}")
        action.status = body.status

    if body.decision is not None:
        if body.decision not in VALID_DECISION:
            raise HTTPException(status_code=422, detail=f"Invalid decision. Use one of: {sorted(VALID_DECISION)}")
        action_center.record_decision(db, user, action, body.decision, note=body.note)
        db.refresh(action)
        db.refresh(doc)
        return action

    action.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(action)
    return action


@router.get("/actions/{action_id}", response_model=schemas.ActionItemOut)
def get_action(action_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    action = db.query(models.ActionItem).filter(models.ActionItem.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Action item not found.")
    _get_owned_document(db, action.document_id, user)
    return action
