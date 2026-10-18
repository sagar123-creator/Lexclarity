"""
Deadline tracker + obligation compliance API.

Reminders are created ONLY by explicit user request (never automatically)
and are an in-app workflow — no external notifications are sent (see README
for what real scheduling would require). Obligations get a user-defined
task status for compliance tracking.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.api.auth import get_current_user
from app.api.upload import _get_owned_document

router = APIRouter(prefix="/api", tags=["deadlines"])

VALID_REMINDER_STATUS = {"pending", "completed", "dismissed"}
VALID_TASK_STATUS = {"pending", "in_progress", "completed"}


@router.get("/documents/{document_id}/reminders", response_model=list[schemas.ReminderOut])
def list_reminders(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    return (
        db.query(models.Reminder)
        .filter(models.Reminder.document_id == doc.id)
        .order_by(models.Reminder.created_at.desc())
        .all()
    )


@router.post("/documents/{document_id}/reminders", response_model=schemas.ReminderOut)
def create_reminder(document_id: str, body: schemas.ReminderCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)

    title = body.title
    due_date = body.due_date
    due_date_kind = None
    date_id = body.date_id

    if date_id:
        important_date = (
            db.query(models.ImportantDate)
            .filter(models.ImportantDate.id == date_id, models.ImportantDate.document_id == doc.id)
            .first()
        )
        if not important_date:
            raise HTTPException(status_code=404, detail="Date not found for this document.")
        date_id = important_date.id
        title = title or f"Reminder: {important_date.label}"
        due_date = due_date or important_date.normalized_date or important_date.date_value
        due_date_kind = important_date.date_kind
    else:
        date_id = None

    if not title or not title.strip():
        raise HTTPException(status_code=422, detail="A reminder title is required.")

    reminder = models.Reminder(
        document_id=doc.id,
        date_id=date_id,
        title=title.strip()[:200],
        due_date=due_date,
        due_date_kind=due_date_kind,
        note=body.note,
        status="pending",
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


@router.patch("/reminders/{reminder_id}", response_model=schemas.ReminderOut)
def update_reminder(reminder_id: str, body: schemas.ReminderUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    reminder = db.query(models.Reminder).filter(models.Reminder.id == reminder_id).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    _get_owned_document(db, reminder.document_id, user)

    if body.title is not None:
        reminder.title = body.title.strip()[:200] or reminder.title
    if body.due_date is not None:
        reminder.due_date = body.due_date
    if body.note is not None:
        reminder.note = body.note
    if body.status is not None:
        if body.status not in VALID_REMINDER_STATUS:
            raise HTTPException(status_code=422, detail=f"Invalid status. Use one of: {sorted(VALID_REMINDER_STATUS)}")
        reminder.status = body.status
    db.commit()
    db.refresh(reminder)
    return reminder


@router.delete("/reminders/{reminder_id}")
def delete_reminder(reminder_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    reminder = db.query(models.Reminder).filter(models.Reminder.id == reminder_id).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    _get_owned_document(db, reminder.document_id, user)
    db.delete(reminder)
    db.commit()
    return {"deleted": True}


@router.patch("/obligations/{obligation_id}", response_model=schemas.ObligationOut)
def update_obligation(obligation_id: str, body: schemas.ObligationUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    obligation = db.query(models.Obligation).filter(models.Obligation.id == obligation_id).first()
    if not obligation:
        raise HTTPException(status_code=404, detail="Obligation not found.")
    _get_owned_document(db, obligation.document_id, user)

    if body.task_status is not None:
        if body.task_status not in VALID_TASK_STATUS:
            raise HTTPException(status_code=422, detail=f"Invalid task_status. Use one of: {sorted(VALID_TASK_STATUS)}")
        obligation.task_status = body.task_status
    db.commit()
    db.refresh(obligation)
    return obligation
