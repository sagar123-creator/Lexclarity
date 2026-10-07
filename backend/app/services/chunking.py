"""
Chunking strategy for RAG.

Rather than splitting on a fixed character window (which cuts sentences and
clauses in half), we:
  1. Clean each page's text.
  2. Split into sentences.
  3. Greedily pack sentences into chunks up to CHUNK_SIZE_TOKENS (approximated
     as whitespace-split words, ~0.75 tokens/word is close enough here).
  4. Carry CHUNK_OVERLAP_TOKENS worth of trailing sentences into the next
     chunk so semantic context isn't lost at chunk boundaries.
  5. Track the page number a chunk started on, and the most recent detected
     section heading, for citations.
"""
from dataclasses import dataclass, field

from app.config import settings
from app.services.document_parser import PageText
from app.utils.text_cleaning import clean_text, split_into_sentences, detect_heading


@dataclass
class Chunk:
    text: str
    page_number: int
    section_heading: str | None
    chunk_index: int
    token_count: int


def _word_count(s: str) -> int:
    return len(s.split())


def chunk_pages(pages: list[PageText]) -> list[Chunk]:
    chunk_size = settings.CHUNK_SIZE_TOKENS
    overlap = settings.CHUNK_OVERLAP_TOKENS

    # Flatten to a stream of (sentence, page_number) while tracking headings
    sentence_stream: list[tuple[str, int, str | None]] = []
    current_heading: str | None = None

    for page in pages:
        cleaned = clean_text(page.text)
        if not cleaned:
            continue
        for line in cleaned.split("\n"):
            heading = detect_heading(line)
            if heading:
                current_heading = heading
                continue
            for sentence in split_into_sentences(line):
                sentence_stream.append((sentence, page.page_number, current_heading))

    chunks: list[Chunk] = []
    buffer: list[tuple[str, int, str | None]] = []
    buffer_words = 0
    idx = 0

    def flush():
        nonlocal buffer, buffer_words, idx
        if not buffer:
            return
        text = " ".join(s for s, _, _ in buffer)
        page_number = buffer[0][1]
        heading = next((h for _, _, h in buffer if h), None)
        chunks.append(Chunk(
            text=text,
            page_number=page_number,
            section_heading=heading,
            chunk_index=idx,
            token_count=buffer_words,
        ))
        idx += 1

    for sentence, page_number, heading in sentence_stream:
        words = _word_count(sentence)
        if buffer_words + words > chunk_size and buffer:
            flush()
            # carry overlap: keep trailing sentences worth ~overlap words
            carried: list[tuple[str, int, str | None]] = []
            carried_words = 0
            for item in reversed(buffer):
                carried_words += _word_count(item[0])
                carried.insert(0, item)
                if carried_words >= overlap:
                    break
            buffer = carried
            buffer_words = carried_words
        buffer.append((sentence, page_number, heading))
        buffer_words += words

    flush()
    return chunks
