from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.api.auth import get_current_user
from app.api.upload import _get_owned_document
from app.services.pipeline import process_document

router = APIRouter(prefix="/api/documents", tags=["analysis"])


@router.post("/{document_id}/analyze", response_model=schemas.AnalysisStatusOut)
def trigger_analysis(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Manually (re)trigger the processing pipeline, e.g. after a failure."""
    doc = _get_owned_document(db, document_id, user)
    if doc.status in ("extracting", "chunking", "embedding", "analyzing"):
        return schemas.AnalysisStatusOut(document_id=doc.id, status=doc.status)
    process_document(db, doc)
    db.refresh(doc)
    return schemas.AnalysisStatusOut(document_id=doc.id, status=doc.status, error_message=doc.error_message)


@router.get("/{document_id}/summary", response_model=schemas.SummaryOut)
def get_summary(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    _require_ready(doc)

    analysis = db.query(models.DocumentAnalysis).filter(models.DocumentAnalysis.document_id == doc.id).first()
    entities = db.query(models.Entity).filter(models.Entity.document_id == doc.id).all()
    obligations = db.query(models.Obligation).filter(models.Obligation.document_id == doc.id).all()
    dates = db.query(models.ImportantDate).filter(models.ImportantDate.document_id == doc.id).all()

    return schemas.SummaryOut(
        executive_summary=analysis.executive_summary if analysis else None,
        document_type=analysis.document_type if analysis else doc.document_type,
        plain_english_overview=analysis.plain_english_overview if analysis else None,
        entities=[schemas.EntityOut.model_validate(e) for e in entities],
        obligations=[schemas.ObligationOut.model_validate(o) for o in obligations],
        important_dates=[schemas.ImportantDateOut.model_validate(d) for d in dates],
    )


@router.get("/{document_id}/risks", response_model=list[schemas.RiskOut])
def get_risks(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    _require_ready(doc)
    risks = (
        db.query(models.Risk)
        .filter(models.Risk.document_id == doc.id)
        .order_by(models.Risk.level.desc())
        .all()
    )
    return risks


@router.get("/{document_id}/clauses", response_model=list[schemas.ClauseOut])
def get_clauses(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    _require_ready(doc)
    return db.query(models.Clause).filter(models.Clause.document_id == doc.id).all()


def _require_ready(doc: models.Document):
    if doc.status == "failed":
        raise HTTPException(status_code=422, detail=doc.error_message or "Document processing failed.")
    if doc.status != "ready":
        raise HTTPException(status_code=409, detail=f"Document is still processing (status: {doc.status}).")
