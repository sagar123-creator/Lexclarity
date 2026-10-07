from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.api.auth import get_current_user
from app.utils.file_validation import validate_upload, sanitize_filename, build_storage_path, new_id
from app.services.pipeline import process_document

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=schemas.UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    contents = await file.read()
    ext = validate_upload(file, len(contents))
    filename = sanitize_filename(file.filename)

    document_id = new_id()
    storage_path = build_storage_path(document_id, ext)
    with open(storage_path, "wb") as f:
        f.write(contents)

    document = models.Document(
        id=document_id,
        user_id=user.id,
        filename=filename,
        file_type=ext.lstrip("."),
        file_size_bytes=len(contents),
        storage_path=storage_path,
        status="uploaded",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # Kick off the processing pipeline asynchronously so the upload request
    # returns immediately; the frontend polls GET /api/documents/{id}.
    background_tasks.add_task(_run_pipeline_with_own_session, document.id)

    return schemas.UploadResponse(
        document=schemas.DocumentOut.model_validate(document),
        message="Upload received. Processing has started.",
    )


def _run_pipeline_with_own_session(document_id: str):
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        document = db.query(models.Document).filter(models.Document.id == document_id).first()
        if document:
            process_document(db, document)
    finally:
        db.close()


@router.get("", response_model=list[schemas.DocumentOut])
def list_documents(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    docs = (
        db.query(models.Document)
        .filter(models.Document.user_id == user.id)
        .order_by(models.Document.created_at.desc())
        .all()
    )
    return docs


@router.get("/{document_id}", response_model=schemas.DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    return doc


def _get_owned_document(db: Session, document_id: str, user: models.User) -> models.Document:
    """Central ownership check reused by every endpoint that touches a document."""
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    if doc.user_id != user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this document.")
    return doc
