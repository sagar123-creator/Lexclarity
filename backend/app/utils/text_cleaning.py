import re


def clean_text(text: str) -> str:
    """Normalize whitespace and strip common PDF extraction artifacts."""
    if not text:
        return ""
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse hyphenated line-wraps: "confiden-\ntiality" -> "confidentiality"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse runs of spaces/tabs
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Strip trailing/leading whitespace per line
    lines = [ln.strip() for ln in text.split("\n")]
    text = "\n".join(lines)
    return text.strip()


_SENTENCE_SPLIT_RE = re.compile(
    r"(?<!\b[A-Z])(?<!\bMr)(?<!\bMs)(?<!\bDr)(?<!\bInc)(?<!\bLtd)(?<!\bCo)"
    r"(?<=[.?!])\s+(?=[A-Z0-9\"'“])"
)


def split_into_sentences(text: str) -> list[str]:
    """Lightweight, dependency-free sentence splitter tuned for legal text.

    Legal documents are full of abbreviations (Inc., Ltd., Sec.) that break
    naive splitters; this uses a few heuristics to reduce false splits and
    also splits on common enumerated-clause patterns (e.g. "1.2 ", "(a) ").
    """
    if not text:
        return []
    # First split on paragraph boundaries to keep clause numbering intact
    paragraphs = [p for p in text.split("\n") if p.strip()]
    sentences: list[str] = []
    for para in paragraphs:
        parts = _SENTENCE_SPLIT_RE.split(para)
        for part in parts:
            part = part.strip()
            if part:
                sentences.append(part)
    return sentences


HEADING_PATTERN = re.compile(
    r"^\s*(?:(\d{1,2}(?:\.\d{1,2})*)[.\)]?\s+)?"
    r"([A-Z][A-Za-z /&\-]{3,60})\s*$"
)


def detect_heading(line: str) -> str | None:
    """Heuristically detect a section heading like '12. Termination' or
    'ARTICLE 5 — CONFIDENTIALITY'. Returns the heading string or None."""
    line = line.strip()
    if not line or len(line) > 80:
        return None
    if line.isupper() and 3 < len(line) < 80:
        return line.title()
    match = HEADING_PATTERN.match(line)
    if match and match.group(1):
        return line
    return None
