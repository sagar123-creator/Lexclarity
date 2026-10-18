"""
Evidence handling: locating quotations inside source text, validating
citations, and building citation payloads that always come from real
source metadata (never invented page numbers, quotes, or references).

Every "found" quote gets character offsets so the evidence viewer can
highlight the exact passage on the original page.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app import models


@dataclass
class QuoteLocation:
    """Where a quote was found in a source text."""
    found: bool
    char_start: int | None = None
    char_end: int | None = None
    exact: bool = True          # True = literal match; False = fuzzy match
    match_ratio: float = 1.0


def _normalize(text: str) -> str:
    """Normalize for comparison: unicode NFC, unify quotes/dashes/whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def find_quote(quote: str, source_text: str, fuzzy_threshold: float = 0.75) -> QuoteLocation:
    """Try to locate `quote` inside `source_text`.

    1. Exact match after whitespace normalization.
    2. Otherwise a fuzzy window match via SequenceMatcher; accepted only when
       the ratio clears `fuzzy_threshold`.
    3. Otherwise reported as not found (which downstream marks the citation
       unverified — we never pretend a quote exists).
    """
    if not quote or not source_text:
        return QuoteLocation(found=False)

    norm_quote = _normalize(quote)
    norm_source = _normalize(source_text)
    if not norm_quote:
        return QuoteLocation(found=False)

    idx = norm_source.find(norm_quote)
    if idx != -1:
        # Map back to approximate offsets in the original text by scaling the
        # normalized index via a position map.
        start, end = _map_normalized_offsets(source_text, idx, idx + len(norm_quote))
        return QuoteLocation(found=True, char_start=start, char_end=end, exact=True, match_ratio=1.0)

    # Fuzzy: slide a window of roughly the quote's length and score it.
    q_words = norm_quote.split()
    if len(q_words) < 3:
        return QuoteLocation(found=False)
    s_words = norm_source.split()
    window = len(q_words) + 2
    best_ratio, best_span = 0.0, None
    for i in range(max(1, len(s_words) - window + 2)):
        candidate = " ".join(s_words[i:i + window])
        ratio = SequenceMatcher(None, norm_quote, candidate).ratio()
        if ratio > best_ratio:
            best_ratio, best_span = ratio, (i, min(i + window, len(s_words)))
    if best_span and best_ratio >= fuzzy_threshold:
        # Convert word offsets back to char offsets in original text.
        start = _word_index_to_char(norm_source, norm_quote, s_words, best_span[0])
        end = _word_index_to_char(norm_source, norm_quote, s_words, best_span[1])
        return QuoteLocation(found=True, char_start=start, char_end=end, exact=False, match_ratio=round(best_ratio, 3))
    return QuoteLocation(found=False, match_ratio=round(best_ratio, 3))


def _map_normalized_offsets(original: str, norm_start: int, norm_end: int) -> tuple[int, int]:
    """Approximate original-text offsets for a span found in normalized text.

    Walks the original string, counting normalized characters, until the
    normalized span boundaries are reached.
    """
    def advance(target: int) -> int:
        count = 0
        prev_ws = False
        for pos, ch in enumerate(original):
            if unicodedata.category(ch).startswith("M"):
                continue
            if ch.isspace():
                if prev_ws or count >= target:
                    prev_ws = True
                    if count >= target:
                        return pos
                    continue
                count += 1
                prev_ws = True
            else:
                count += 1
                prev_ws = False
            if count >= target:
                return pos + 1
        return len(original)

    return advance(norm_start), advance(norm_end)


def _word_index_to_char(norm_source: str, norm_quote: str, s_words: list[str], word_idx: int) -> int:
    if word_idx <= 0:
        return 0
    prefix = " ".join(s_words[:word_idx])
    idx = norm_source.find(prefix)
    if idx == -1:
        return 0
    return idx + len(prefix)


def get_page(db: Session, document_id: str, page_number: int) -> models.DocumentPage | None:
    return (
        db.query(models.DocumentPage)
        .filter(models.DocumentPage.document_id == document_id, models.DocumentPage.page_number == page_number)
        .first()
    )


def get_chunk(db: Session, document_id: str, chunk_id: str) -> models.DocumentChunk | None:
    return (
        db.query(models.DocumentChunk)
        .filter(models.DocumentChunk.id == chunk_id, models.DocumentChunk.document_id == document_id)
        .first()
    )


def build_citation(
    db: Session,
    document_id: str,
    chunk_id: str | None = None,
    page_number: int | None = None,
    quote: str | None = None,
) -> dict:
    """Build a citation dict from real source metadata.

    Never invents page numbers: page_number is taken from the chunk record
    when available, else left None. If a quote is supplied it is validated
    against the chunk/page text; the citation is flagged when it can't be
    verified.
    """
    citation: dict = {
        "document_id": document_id,
        "chunk_id": None,
        "page_number": None,
        "section_reference": None,
        "snippet": None,
        "quote_verified": None,
    }

    chunk = get_chunk(db, document_id, chunk_id) if chunk_id else None
    if chunk:
        citation["chunk_id"] = chunk.id
        citation["page_number"] = chunk.page_number
        citation["section_reference"] = chunk.section_heading
        citation["snippet"] = chunk.text[:220] + ("…" if len(chunk.text) > 220 else "")

    if page_number is not None and citation["page_number"] is None:
        page = get_page(db, document_id, page_number)
        if page:  # only accept a page number that actually exists
            citation["page_number"] = page.page_number

    if quote:
        citation["quote"] = quote
        source_text = chunk.text if chunk else None
        if source_text is None and citation["page_number"] is not None:
            page = get_page(db, document_id, citation["page_number"])
            source_text = page.text if page else None
        if source_text:
            loc = find_quote(quote, source_text)
            citation["quote_verified"] = loc.found
            if loc.found:
                citation["char_start"], citation["char_end"] = loc.char_start, loc.char_end
        else:
            citation["quote_verified"] = False

    return citation


def validate_finding_citation(
    db: Session, document_id: str, chunk_id: str | None, quote: str | None
) -> tuple[bool, int | None, int | None, str]:
    """Validate that a finding's quote exists in its claimed source chunk.

    Returns (verified, char_start, char_end, note). Used by the risk/clause
    pipeline so findings without genuine textual support are flagged rather
    than presented as facts.
    """
    if not chunk_id:
        return False, None, None, "No source chunk was recorded for this finding."
    chunk = get_chunk(db, document_id, chunk_id)
    if chunk is None:
        return False, None, None, "The cited source chunk does not exist in this document."
    if not quote:
        return False, None, None, "No supporting quotation was provided."
    loc = find_quote(quote, chunk.text)
    if not loc.found:
        return False, None, None, (
            "The quoted text could not be located in the cited source passage "
            f"(best fuzzy match {loc.match_ratio:.2f})."
        )
    note = "Quotation verified verbatim in source passage." if loc.exact else (
        f"Quotation located in source passage via fuzzy match ({loc.match_ratio:.2f}); "
        "please review the original page."
    )
    return True, loc.char_start, loc.char_end, note
