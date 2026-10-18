"""
Accuracy Evaluation API.

`GET /api/evaluation/status` returns the most recent completed run's real
metrics, or {"evaluated": false} when no evaluation has run — the dashboard
shows "Not evaluated" in that case. Never invents metrics.
"""
import os

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings
from app.database import get_db
from app.api.auth import get_current_user
from app.services.evaluation import run_evaluation

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.get("/runs", response_model=list[schemas.EvaluationRunOut])
def list_runs(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return (
        db.query(models.EvaluationRun)
        .order_by(models.EvaluationRun.started_at.desc())
        .limit(20)
        .all()
    )


@router.get("/status")
def status(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    run = (
        db.query(models.EvaluationRun)
        .filter(models.EvaluationRun.status == "completed")
        .order_by(models.EvaluationRun.started_at.desc())
        .first()
    )
    if not run:
        return {"evaluated": False, "message": "Not evaluated — no completed evaluation run exists."}
    return {
        "evaluated": True,
        "run_id": run.id,
        "dataset_name": run.dataset_name,
        "metrics": run.metrics,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


@router.post("/run", response_model=schemas.EvaluationRunOut)
def trigger_run(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Run the evaluation framework against the configured labelled dataset.

    This executes the REAL pipeline (including LLM calls) and can take several
    minutes; the response returns the persisted run record with computed metrics.
    """
    if not os.path.exists(settings.EVAL_DATASET_PATH):
        raise HTTPException(status_code=422, detail=f"Dataset not found: {settings.EVAL_DATASET_PATH}")
    return run_evaluation(db)
