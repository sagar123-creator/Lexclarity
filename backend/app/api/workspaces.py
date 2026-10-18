"""
Multi-document case workspace API.

Workspace retrieval is scoped to the workspace's documents, and every
document in a workspace must belong to the requesting user — one user's
documents are never exposed to another user.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.api.auth import get_current_user
from app.api.upload import _get_owned_document
from app.services import workspace_service

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def _get_owned_workspace(db: Session, workspace_id: str, user: models.User) -> models.Workspace:
    ws = db.query(models.Workspace).filter(models.Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if ws.user_id != user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this workspace.")
    return ws


@router.get("", response_model=list[schemas.WorkspaceOut])
def list_workspaces(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return (
        db.query(models.Workspace)
        .filter(models.Workspace.user_id == user.id)
        .order_by(models.Workspace.created_at.desc())
        .all()
    )


@router.post("", response_model=schemas.WorkspaceOut)
def create_workspace(body: schemas.WorkspaceCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if not body.name or not body.name.strip():
        raise HTTPException(status_code=422, detail="Workspace name is required.")
    ws = models.Workspace(user_id=user.id, name=body.name.strip()[:120], description=body.description)
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


@router.get("/{workspace_id}", response_model=schemas.WorkspaceDetailOut)
def get_workspace(workspace_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    ws = _get_owned_workspace(db, workspace_id, user)
    doc_ids = [wd.document_id for wd in ws.documents]
    documents = (
        db.query(models.Document)
        .filter(models.Document.id.in_(doc_ids), models.Document.user_id == user.id)
        .order_by(models.Document.created_at.desc())
        .all()
        if doc_ids else []
    )
    return schemas.WorkspaceDetailOut(
        id=ws.id, name=ws.name, description=ws.description, created_at=ws.created_at,
        documents=[schemas.DocumentOut.model_validate(d) for d in documents],
    )


@router.post("/{workspace_id}/documents", response_model=schemas.WorkspaceDetailOut)
def add_document(workspace_id: str, body: schemas.WorkspaceDocumentAdd, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    ws = _get_owned_workspace(db, workspace_id, user)
    doc = _get_owned_document(db, body.document_id, user)  # enforces ownership
    exists = (
        db.query(models.WorkspaceDocument)
        .filter(models.WorkspaceDocument.workspace_id == ws.id, models.WorkspaceDocument.document_id == doc.id)
        .first()
    )
    if not exists:
        db.add(models.WorkspaceDocument(workspace_id=ws.id, document_id=doc.id))
        db.commit()
    return get_workspace(workspace_id, db, user)


@router.delete("/{workspace_id}/documents/{document_id}", response_model=schemas.WorkspaceDetailOut)
def remove_document(workspace_id: str, document_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    ws = _get_owned_workspace(db, workspace_id, user)
    link = (
        db.query(models.WorkspaceDocument)
        .filter(models.WorkspaceDocument.workspace_id == ws.id, models.WorkspaceDocument.document_id == document_id)
        .first()
    )
    if link:
        db.delete(link)
        db.commit()
    return get_workspace(workspace_id, db, user)


@router.post("/{workspace_id}/search", response_model=schemas.WorkspaceChatResponse)
def search_workspace(workspace_id: str, body: schemas.WorkspaceChatRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    ws = _get_owned_workspace(db, workspace_id, user)
    result = workspace_service.search_workspace(db, ws, body.message)
    return schemas.WorkspaceChatResponse(
        answer=result["answer"],
        citations=[schemas.CitationOut(**c) for c in result["citations"]],
        confidence=result["confidence"],
        conflicts=result.get("conflicts", []),
        verification=result.get("verification"),
    )


@router.get("/{workspace_id}/timeline")
def workspace_timeline(workspace_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    ws = _get_owned_workspace(db, workspace_id, user)
    return {"timeline": workspace_service.cross_document_timeline(db, ws)}


@router.get("/{workspace_id}/obligations")
def workspace_obligations(workspace_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    ws = _get_owned_workspace(db, workspace_id, user)
    return {"obligations": workspace_service.cross_document_obligations(db, ws)}
