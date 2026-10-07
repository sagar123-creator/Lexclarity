"""
Document text extraction.

Returns a list of PageText(page_number, text) so downstream chunking can
attach a page number to every chunk for citation purposes. DOCX/TXT files
don't have a native concept of "pages", so we synthesize approximate pages
by splitting on a character budget — good enough for citation purposes and
clearly documented as approximate.
"""
from dataclasses import dataclass

from fastapi import HTTPException


@dataclass
class PageText:
    page_number: int
    text: str


APPROX_CHARS_PER_PAGE = 3000


def extract_pdf(path: str) -> list[PageText]:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("pypdf is not installed") from e

    try:
        reader = PdfReader(path)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not open PDF (it may be corrupted): {e}")

    if len(reader.pages) == 0:
        raise HTTPException(status_code=422, detail="The PDF has no pages.")

    pages = []
    total_chars = 0
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        total_chars += len(text.strip())
        pages.append(PageText(page_number=i, text=text))

    if total_chars < 20:
        raise HTTPException(
            status_code=422,
            detail=(
                "No extractable text was found in this PDF. It may be a scanned "
                "image without OCR. Try uploading a text-based PDF, or run OCR "
                "on it first."
            ),
        )
    return pages


def extract_docx(path: str) -> list[PageText]:
    try:
        import docx
    except ImportError as e:
        raise RuntimeError("python-docx is not installed") from e

    try:
        document = docx.Document(path)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not open DOCX file (it may be corrupted): {e}")

    full_text = "\n".join(p.text for p in document.paragraphs)
    if len(full_text.strip()) < 20:
        raise HTTPException(status_code=422, detail="The document appears to be empty.")

    return _paginate_flat_text(full_text)


def extract_txt(path: str) -> list[PageText]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read text file: {e}")

    if len(text.strip()) < 20:
        raise HTTPException(status_code=422, detail="The document appears to be empty.")

    return _paginate_flat_text(text)


def _paginate_flat_text(text: str) -> list[PageText]:
    """Split text without native pagination into approximate pages."""
    pages = []
    for i in range(0, len(text), APPROX_CHARS_PER_PAGE):
        chunk = text[i:i + APPROX_CHARS_PER_PAGE]
        pages.append(PageText(page_number=(i // APPROX_CHARS_PER_PAGE) + 1, text=chunk))
    return pages or [PageText(page_number=1, text=text)]


def extract_text(path: str, file_type: str) -> list[PageText]:
    file_type = file_type.lower().lstrip(".")
    if file_type == "pdf":
        return extract_pdf(path)
    if file_type == "docx":
        return extract_docx(path)
    if file_type == "txt":
        return extract_txt(path)
    raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_type}")
