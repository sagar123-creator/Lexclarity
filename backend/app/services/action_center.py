"""
Legal Action Center.

Converts sufficiently supported findings into reviewable action items:

    Risk/Date/Checklist finding -> Evidence -> Explanation -> Suggested Action

Priority is computed deterministically from evidence quality, severity,
urgency and explicit deadlines — recorded as a human-readable reason, never
presented as an objective legal assessment. Actions are drafts: they require
explicit user approval, and LexClarity never performs external actions.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import models

SEVERITY_SCORE = {"High": 3, "Medium": 2, "Low": 1}
SUPPORTED_BONUS = 1
URGENT_DAYS = 30
SOON_DAYS = 90


def _priority_for(score: int) -> str:
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return None


def generate_action_items(db: Session, document: models.Document) -> list[models.ActionItem]:
    """Create action items from the document's findings. Idempotent: an
    action already created for a finding source is not duplicated."""
    existing = {
        (a.source_type, a.source_id)
        for a in db.query(models.ActionItem).filter(models.ActionItem.document_id == document.id).all()
    }
    created: list[models.ActionItem] = []

    # --- Risks ---
    risks = db.query(models.Risk).filter(models.Risk.document_id == document.id).all()
    for risk in risks:
        if ("risk", risk.id) in existing:
            continue
        score = SEVERITY_SCORE.get(risk.level, 1)
        reasons = [f"risk severity {risk.level} (score {SEVERITY_SCORE.get(risk.level, 1)})"]
        if risk.verification_status == "supported":
            score += SUPPORTED_BONUS
            reasons.append("evidence verified against source text")
        elif risk.verification_status in ("needs_review", "insufficient", "contradicted"):
            reasons.append("evidence needs human review before acting")
        action = models.ActionItem(
            document_id=document.id,
            source_type="risk",
            source_id=risk.id,
            title=f"Review: {risk.title}",
            description=(
                f"{risk.description}\n\nWhy it matters: {risk.why_it_matters}\n\n"
                + (f"Severity rationale: {risk.severity_rationale}" if risk.severity_rationale else "")
            ),
            evidence=[{
                "chunk_id": risk.source_chunk_id,
                "page_number": risk.page_number,
                "quote": risk.evidence_quote,
            }] if (risk.evidence_quote or risk.page_number) else [],
            suggested_action=risk.suggested_action,
            priority=_priority_for(score),
            priority_reason="; ".join(reasons),
            required_input=None,
        )
        db.add(action)
        created.append(action)

    # --- Key dates / deadlines ---
    today = datetime.utcnow()
    dates = db.query(models.ImportantDate).filter(models.ImportantDate.document_id == document.id).all()
    for d in dates:
        if ("date", d.id) in existing:
            continue
        normalized = _parse_date(d.normalized_date)
        if normalized is None:
            continue  # only actionable dates become actions
        days_left = (normalized - today).days
        if days_left < 0:
            continue  # past dates are informational, not actions
        score = 2
        reasons = [f"deadline on {normalized.date().isoformat()}"]
        if days_left <= URGENT_DAYS:
            score += 2
            reasons.append(f"due within {URGENT_DAYS} days ({days_left} days left)")
        elif days_left <= SOON_DAYS:
            score += 1
            reasons.append(f"due within {SOON_DAYS} days ({days_left} days left)")
        action = models.ActionItem(
            document_id=document.id,
            source_type="date",
            source_id=d.id,
            title=f"Prepare for: {d.label} ({normalized.date().isoformat()})",
            description=(d.description or "") + (
                f"\n\nNote: this date was {'inferred' if d.date_kind == 'inferred' else 'stated explicitly'} "
                "in the document — please confirm before relying on it."
            ),
            evidence=[{
                "chunk_id": d.source_chunk_id,
                "page_number": d.page_number,
                "quote": d.evidence_quote,
            }] if (d.evidence_quote or d.page_number) else [],
            suggested_action=(
                "Calendar this date, confirm the notice method required by the agreement, "
                "and decide (with your advisor, if appropriate) what to do before the deadline."
            ),
            priority=_priority_for(score),
            priority_reason="; ".join(reasons),
            required_input="Confirm whether this date applies to your side of the agreement.",
        )
        db.add(action)
        created.append(action)

    db.commit()
    for a in created:
        db.refresh(a)
    return created


def record_decision(
    db: Session, user: models.User, action: models.ActionItem, decision: str, note: str | None = None
) -> None:
    """Record the user's decision on an action item, with an audit entry."""
    action.decision = decision
    db.add(models.AuditLog(
        user_id=user.id,
        document_id=action.document_id,
        action="action_item.decision",
        detail={"action_item_id": action.id, "decision": decision, "note": note},
    ))
    db.commit()
