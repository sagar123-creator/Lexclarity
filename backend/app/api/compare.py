"""
Contract comparison API.

Compare two analyzed documents of the same user; the structured result is
persisted so it can be re-read later.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.api.auth import get_current_user
from app.api.upload import _get_owned_document
from app.services.comparator import compare_documents

router = APIRouter(prefix="/api", tags=["compare"])


@router.post("/compare", response_model=schemas.ComparisonOut)
def compare(body: schemas.CompareRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc_a = _get_owned_document(db, body.document_a_id, user)
    doc_b = _get_owned_document(db, body.document_b_id, user)
    if doc_a.id == doc_b.id:
        raise HTTPException(status_code=422, detail="Choose two different documents to compare.")
    for d in (doc_a, doc_b):
        if d.status != "ready":
            raise HTTPException(status_code=409, detail=f"'{d.filename}' is still processing (status: {d.status}).")

    result = compare_documents(db, doc_a, doc_b)
    comparison = models.Comparison(
        user_id=user.id,
        document_a_id=doc_a.id,
        document_b_id=doc_b.id,
        status="ready",
        summary=result,
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)
    return comparison


@router.get("/compare/{comparison_id}", response_model=schemas.ComparisonOut)
def get_comparison(comparison_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    comparison = (
        db.query(models.Comparison)
        .filter(models.Comparison.id == comparison_id, models.Comparison.user_id == user.id)
        .first()
    )
    if not comparison:
        raise HTTPException(status_code=404, detail="Comparison not found.")
    return comparison


@router.get("/compare", response_model=list[schemas.ComparisonOut])
def list_comparisons(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return (
        db.query(models.Comparison)
        .filter(models.Comparison.user_id == user.id)
        .order_by(models.Comparison.created_at.desc())
        .limit(50)
        .all()
    )
