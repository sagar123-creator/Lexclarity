"""
Legal Document Generator API.

Creates editable drafts grounded in the document's findings, supports
editing, listing, and Markdown export. Drafts are clearly labeled as
AI-generated until the user edits them; nothing is ever sent anywhere.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.api.auth import get_current_user
from app.api.upload import _get_owned_document
from app.services import generator

router = APIRouter(prefix="/api", tags=["generator"])


@router.get("/templates")
def list_templates():
    return [
        {"kind": kind, "title": meta["title"], "description": meta["description"]}
        for kind, meta in generator.TEMPLATE_KINDS.items()
    ]


@router.post("/documents/{document_id}/drafts", response_model=schemas.DraftOut)
def create_draft(document_id: str, body: schemas.GenerateDraftRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    if doc.status != "ready":
        raise HTTPException(status_code=409, detail=f"Document is still processing (status: {doc.status}).")

    source_ids = body.source_ids
    if body.action_item_id:
        action = db.query(models.ActionItem).filter(
            models.ActionItem.id == body.action_item_id, models.ActionItem.document_id == doc.id
        ).first()
        if not action:
            raise HTTPException(status_code=404, detail="Action item not found for this document.")
        source_ids = [action.source_id] if action.source_id else []
        if not source_ids:
            raise HTTPException(status_code=422, detail="That action item has no linked finding to ground a draft in.")

    try:
        payload = generator.generate_draft(
            db, doc, body.kind, source_ids=source_ids, user_instructions=body.user_instructions
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    draft = models.Draft(
        document_id=doc.id,
        action_item_id=body.action_item_id,
        kind=payload["kind"],
        title=payload["title"],
        content=payload["content"],
        placeholders=payload["placeholders"],
        source_refs=payload["source_refs"],
        is_ai_generated=True,
        edited_by_user=False,
    )
    db.add(draft)
    if body.action_item_id:
        action = db.query(models.ActionItem).filter(models.ActionItem.id == body.action_item_id).first()
        if action and action.status == "pending":
            action.status = "in_progress"
    db.commit()
    db.refresh(draft)
    return draft


@router.get("/documents/{document_id}/drafts", response_model=list[schemas.DraftOut])
def list_drafts(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    return (
        db.query(models.Draft)
        .filter(models.Draft.document_id == doc.id)
        .order_by(models.Draft.created_at.desc())
        .all()
    )


@router.get("/drafts/{draft_id}", response_model=schemas.DraftOut)
def get_draft(draft_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    draft = db.query(models.Draft).filter(models.Draft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")
    _get_owned_document(db, draft.document_id, user)
    return draft


@router.put("/drafts/{draft_id}", response_model=schemas.DraftOut)
def update_draft(draft_id: str, body: schemas.DraftUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    draft = db.query(models.Draft).filter(models.Draft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")
    _get_owned_document(db, draft.document_id, user)

    if body.title is not None:
        draft.title = body.title.strip()[:200] or draft.title
    if body.content is not None:
        draft.content = body.content
        draft.edited_by_user = True
        draft.placeholders = sorted(set(generator.PLACEHOLDER_RE.findall(body.content)))
    db.commit()
    db.refresh(draft)
    return draft


@router.get("/drafts/{draft_id}/export")
def export_draft(draft_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Markdown export of a draft (also usable for .md download client-side)."""
    draft = db.query(models.Draft).filter(models.Draft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")
    _get_owned_document(db, draft.document_id, user)

    doc = db.query(models.Document).filter(models.Document.id == draft.document_id).first()
    lines = [f"# {draft.title}", ""]
    if draft.is_ai_generated:
        lines += [
            f"> {'Edited by user' if draft.edited_by_user else 'AI-generated draft'} — "
            "review carefully before use. LexClarity does not provide legal advice.",
            "",
        ]
    lines += [f"*Source document: {doc.filename if doc else 'unknown'}*", ""]
    lines.append(draft.content)
    if draft.placeholders:
        lines += ["", "## Placeholders to fill", ""]
        lines += [f"- {p}" for p in draft.placeholders]
    if draft.source_refs:
        lines += ["", "## Sources referenced", ""]
        for ref in draft.source_refs:
            page = f", page {ref['page_number']}" if ref.get("page_number") else ""
            quote = f' — "{ref["quote"]}"' if ref.get("quote") else ""
            lines.append(f"- {ref.get('label', 'finding')}{page}{quote}")

    content = "\n".join(lines)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in draft.title.lower())[:60] or "draft"
    return PlainTextResponse(
        content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.md"'},
    )
