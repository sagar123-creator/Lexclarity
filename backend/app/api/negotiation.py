"""
Contract Negotiation Assistant API.

Generate a negotiation suggestion for a selected clause, and list previous
suggestions. Suggestions are AI-generated — never presented as legally
valid or enforceable.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.api.auth import get_current_user
from app.api.upload import _get_owned_document
from app.services.negotiation import suggest_negotiation

router = APIRouter(prefix="/api", tags=["negotiation"])


@router.post("/documents/{document_id}/negotiate", response_model=schemas.ClauseSuggestionOut)
def negotiate(document_id: str, body: schemas.NegotiateRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    if doc.status not in ("ready", "stopped"):
        raise HTTPException(status_code=409, detail=f"Document is still processing (status: {doc.status}).")
    clause = (
        db.query(models.Clause)
        .filter(models.Clause.id == body.clause_id, models.Clause.document_id == doc.id)
        .first()
    )
    if not clause:
        raise HTTPException(status_code=404, detail="Clause not found in this document.")
    try:
        return suggest_negotiation(db, doc, clause)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/documents/{document_id}/negotiate", response_model=list[schemas.ClauseSuggestionOut])
def list_suggestions(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    return (
        db.query(models.ClauseSuggestion)
        .filter(models.ClauseSuggestion.document_id == doc.id)
        .order_by(models.ClauseSuggestion.created_at.desc())
        .all()
    )
