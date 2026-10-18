"""
Executive summary + document type classification.

Long documents are never sent to the LLM in full. Instead we sample a
representative spread of chunks (first chunks + chunks most similar to a
"what is this document about" query) to stay within context limits while
still grounding the summary in the actual text.
"""
from app.services.embeddings import embed_query
from app.services.vector_store import get_vector_store
from app.services.llm import complete_json

DOCUMENT_TYPES = [
    "Employment Agreement", "Rental Agreement", "NDA", "Service Agreement",
    "Purchase Agreement", "Loan Agreement", "Partnership Agreement", "Other",
]

SYSTEM_PROMPT = (
    "You are LexClarity, an AI legal-document analysis assistant. You summarize "
    "documents strictly based on the excerpts you are given. You never invent "
    "facts, and you never provide definitive legal advice. Use cautious, "
    "descriptive language."
)


def _representative_chunks(document_id: str, all_chunks: list[dict], max_chunks: int = 8) -> list[dict]:
    if len(all_chunks) <= max_chunks:
        return all_chunks

    store = get_vector_store()
    query_emb = embed_query(
        "overview of the agreement, purpose, parties, main terms and conditions"
    )
    retrieved = store.query(document_id, query_emb, top_k=max_chunks // 2)
    retrieved_ids = {r.chunk_id for r in retrieved}

    head = all_chunks[: max_chunks // 2]
    extra = [c for c in all_chunks if c["chunk_id"] in retrieved_ids and c not in head]
    combined = head + extra
    return combined[:max_chunks]


def _format_chunks(chunks: list[dict]) -> str:
    return "\n\n".join(
        f"[page={c['page_number']}] {c['text']}" for c in chunks
    )


def summarize_document(document_id: str, all_chunks: list[dict]) -> dict:
    """Returns {executive_summary, document_type, plain_english_overview}."""
    sample = _representative_chunks(document_id, all_chunks)
    context = _format_chunks(sample)

    prompt = f"""Document excerpts (this is a partial sample of a longer document):
{context}

Based ONLY on these excerpts, produce a JSON object:
{{
  "document_type": one of {DOCUMENT_TYPES},
  "executive_summary": "3-5 sentence plain-English summary of what this document is and its main purpose",
  "plain_english_overview": "a slightly longer (1-2 paragraph) plain-English walkthrough of the document's key terms"
}}

Be cautious and descriptive rather than definitive. Do not invent details not present in the excerpts."""

    result = complete_json(SYSTEM_PROMPT, prompt, max_tokens=2000)
    if isinstance(result, dict):
        return result
    # The model ran but did not return a valid summary object — a content
    # (not provider) error the pipeline records without faking a summary.
    return {"document_type": "Other", "executive_summary": None,
            "plain_english_overview": None,
            "error": "The model did not return a valid summary object."}
