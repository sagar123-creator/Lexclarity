"""
Legal Action Plan API.

Returns a prioritized, evidence-grounded plan built from the document's
action items. Priority reasons are recorded strings — the plan explicitly
states it is not an objective legal assessment.
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.api.auth import get_current_user
from app.api.upload import _get_owned_document

router = APIRouter(prefix="/api", tags=["plan"])

_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

DISCLAIMER = (
    "This plan prioritizes items using documented criteria (evidence quality, "
    "severity, urgency, explicit deadlines). It is a workflow aid, not an "
    "objective legal assessment. Confirm priorities with a qualified advisor."
)


@router.get("/documents/{document_id}/plan", response_model=schemas.ActionPlanOut)
def get_plan(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    actions = (
        db.query(models.ActionItem)
        .filter(models.ActionItem.document_id == doc.id)
        .all()
    )
    actions.sort(key=lambda a: (_PRIORITY_ORDER.get(a.priority, 3), a.created_at))

    items = [
        schemas.PlanItemOut(
            action_id=a.id,
            title=a.title,
            priority=a.priority,
            priority_reason=a.priority_reason,
            related_finding_type=a.source_type,
            suggested_action=a.suggested_action,
            required_input=a.required_input,
            status=a.status,
            decision=a.decision,
            evidence=a.evidence,
        )
        for a in actions
    ]
    return schemas.ActionPlanOut(
        document_id=doc.id,
        generated_at=datetime.utcnow(),
        items=items,
        disclaimer=DISCLAIMER,
    )
