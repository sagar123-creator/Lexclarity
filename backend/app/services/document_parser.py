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

from app.config import settings


@dataclass
class PageText:
    page_number: int
    text: str
    ocr_used: bool = False  # True when text came from OCR (quality may vary)


APPROX_CHARS_PER_PAGE = 3000


def _ocr_pdf_pages(path: str, page_numbers: list[int]) -> dict[int, str]:
    """OCR specific PDF pages using PyMuPDF (render) + Tesseract (recognize).

    Both dependencies are optional: if either is unavailable we return an
    empty dict and the caller reports a clear, actionable message. Tesseract
    itself must be installed on the system (see README).
    """
    if not settings.OCR_ENABLED:
        return {}
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return {}
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return {}

    results: dict[int, str] = {}
    try:
        with fitz.open(path) as doc:
            for page_idx in page_numbers:
                if page_idx >= len(doc):
                    continue
                page = doc.load_page(page_idx)
                pix = page.get_pixmap(dpi=250)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                text = pytesseract.image_to_string(img, lang=settings.OCR_LANG)
                if text and text.strip():
                    results[page_idx] = text
    except Exception:  # noqa: BLE001 - OCR must never crash the pipeline
        return results
    return results


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
    empty_page_indices: list[int] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        total_chars += len(text.strip())
        if len(text.strip()) < 10:
            empty_page_indices.append(i - 1)
        pages.append(PageText(page_number=i, text=text))

    ocr_used_any = False
    if total_chars < 20 or (empty_page_indices and total_chars < 0.3 * len(reader.pages) * 1000):
        # Likely a scanned document (or mostly-image pages): try OCR fallback.
        ocr_results = _ocr_pdf_pages(path, empty_page_indices if total_chars >= 20 else list(range(len(reader.pages))))
        for page_idx, ocr_text in ocr_results.items():
            existing = pages[page_idx]
            if len(existing.text.strip()) < 10:
                pages[page_idx] = PageText(
                    page_number=existing.page_number, text=ocr_text, ocr_used=True
                )
                ocr_used_any = True
                total_chars += len(ocr_text.strip())

    if total_chars < 20:
        ocr_hint = ""
        if settings.OCR_ENABLED:
            ocr_hint = (
                " Automatic OCR was attempted but is unavailable — install the OCR "
                "dependencies (`pip install pymupdf pytesseract`) and the Tesseract "
                "binary, then retry."
            )
        else:
            ocr_hint = " Automatic OCR is disabled (OCR_ENABLED=false)."
        raise HTTPException(
            status_code=422,
            detail=(
                "No extractable text was found in this PDF. It may be a scanned "
                f"image without a usable OCR layer.{ocr_hint}"
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
