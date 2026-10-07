import os
import re
import uuid

from fastapi import UploadFile, HTTPException

from app.config import settings


def sanitize_filename(filename: str) -> str:
    """Strip path components and dangerous characters from a filename."""
    filename = os.path.basename(filename)
    filename = re.sub(r"[^A-Za-z0-9._ -]", "_", filename)
    return filename[:200] or "document"


def validate_upload(file: UploadFile, size_bytes: int) -> str:
    """Validate extension and size. Returns the normalized extension (e.g. '.pdf')."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed types: PDF, DOCX, TXT.",
        )
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File is too large. Maximum allowed size is {settings.MAX_FILE_SIZE_MB}MB.",
        )
    if size_bytes == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    return ext


def build_storage_path(document_id: str, ext: str) -> str:
    safe_dir = os.path.join(settings.UPLOAD_DIR)
    os.makedirs(safe_dir, exist_ok=True)
    return os.path.join(safe_dir, f"{document_id}{ext}")


def new_id() -> str:
    return str(uuid.uuid4())
