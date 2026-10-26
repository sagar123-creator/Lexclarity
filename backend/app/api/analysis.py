from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.api.auth import get_current_user
from app.api.upload import _get_owned_document
from app.services import cancellation
from app.services.pipeline import process_document

router = APIRouter(prefix="/api/documents", tags=["analysis"])

# Statuses in which a pipeline run owns the document — the brief "uploaded"
# window (background task queued but not started) is included, so an analysis
# can be stopped before it has done any work.
ACTIVE_STATUSES = ("uploaded", "extracting", "chunking", "embedding", "analyzing")


@router.post("/{document_id}/analyze", response_model=schemas.AnalysisStatusOut)
def trigger_analysis(
    document_id: str,
    full: bool = False,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Manually (re)trigger the processing pipeline, e.g. after a failure.

    By default a re-run *resumes*: sections that already produced results are
    kept and only the missing ones are retried, so a retry while the provider's
    per-day quota is scarce actually reaches them instead of re-spending the
    budget on sections that already work. Pass ``?full=true`` to rebuild the
    whole analysis from scratch.
    """
    doc = _get_owned_document(db, document_id, user)
    if doc.status in ACTIVE_STATUSES:
        return schemas.AnalysisStatusOut(document_id=doc.id, status=doc.status)
    # A deliberately-started run always begins from a clean slate: drop any stop
    # request left over from the run the user is now asking us to (re)start.
    cancellation.clear_stop(doc.id)
    process_document(db, doc, resume_missing=not full)
    db.refresh(doc)
    return schemas.AnalysisStatusOut(document_id=doc.id, status=doc.status, error_message=doc.error_message)


@router.post("/{document_id}/stop", response_model=schemas.AnalysisStatusOut)
def stop_analysis(
    document_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Stop processing this document.

    Stopping is cooperative: a run that is actually in flight settles as
    ``stopped`` at its next stage boundary (an LLM call already under way
    finishes first), so the status here may still read ``analyzing`` for a few
    seconds — the UI polls ``GET /api/documents/{id}`` until it settles.
    Everything written before the stop is kept, and resuming re-runs only the
    sections that are still missing.

    A document whose status says it is processing but has *no* live run (a row
    left behind by a restart) is settled immediately instead of waiting for a
    boundary that will never come.
    """
    doc = _get_owned_document(db, document_id, user)
    if doc.status == "stopped":
        return schemas.AnalysisStatusOut(document_id=doc.id, status=doc.status, error_message=doc.error_message)
    if doc.status not in ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail=f"Document is not being processed (status: {doc.status}).")

    cancellation.request_stop(doc.id)
    if not cancellation.is_running(doc.id):
        doc.status = "stopped"
        doc.error_message = cancellation.STOPPED_MESSAGE
        db.commit()
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
    # A stopped document keeps whatever its completed stages produced, so the
    # partial results stay readable (the UI shows a "stopped" banner over them
    # and offers to resume the analysis).
    if doc.status not in ("ready", "stopped"):
        raise HTTPException(status_code=409, detail=f"Document is still processing (status: {doc.status}).")
