"""
Structured extraction: entities, obligations, dates, and key clauses.

Strategy: rather than sending the whole document to the LLM in one shot
(expensive, lossy, and prone to hallucination on long documents), we use the
already-chunked, embedded text and retrieve the chunks most relevant to each
extraction target via semantic search, then ask the LLM to extract
structured JSON grounded ONLY in those chunks, always carrying page/section
metadata through so every extracted item can cite its source.
"""
from app.services.embeddings import embed_query
from app.services.vector_store import get_vector_store
from app.services.llm import complete_json, LLMError
from app.config import settings

EXTRACTION_QUERIES = {
    "entities": "parties to the agreement, company names, individual names, signatories",
    "obligations": "obligations, duties, responsibilities, must provide, shall perform, required to",
    "dates": "effective date, start date, end date, term, renewal, notice period, deadlines, payment due dates",
    "clauses": (
        "termination, payment terms, confidentiality, liability, indemnification, "
        "intellectual property, non-compete, dispute resolution, governing law, "
        "renewal, penalties"
    ),
}


def _gather_context(document_id: str, query: str, top_k: int = 10) -> list[dict]:
    store = get_vector_store()
    query_emb = embed_query(query)
    results = store.query(document_id, query_emb, top_k=top_k)
    return [
        {"chunk_id": r.chunk_id, "text": r.text, "page_number": r.page_number, "section": r.section_heading}
        for r in results
    ]


def _format_context(chunks: list[dict]) -> str:
    blocks = []
    for c in chunks:
        header = f"[chunk_id={c['chunk_id']} page={c['page_number']} section={c.get('section') or 'n/a'}]"
        blocks.append(f"{header}\n{c['text']}")
    return "\n\n".join(blocks)


SYSTEM_BASE = (
    "You are a legal-document extraction engine. You only extract information "
    "that is explicitly present in the provided document excerpts. Never invent "
    "names, dates, or obligations. If nothing relevant is found, return an empty "
    "list. Always include the chunk_id and page_number of the excerpt that "
    "supports each extracted item, copied exactly from the excerpt headers."
)


def extract_entities(document_id: str) -> list[dict]:
    chunks = _gather_context(document_id, EXTRACTION_QUERIES["entities"])
    if not chunks:
        return []
    prompt = f"""Document excerpts:
{_format_context(chunks)}

Extract every party/entity involved in this agreement (companies and individuals).
Return a JSON array of objects: [{{"name": str, "role": str, "entity_type": "organization"|"individual"}}]
"role" should be their role in the agreement (e.g. "Employer", "Tenant", "Service Provider").
Only include entities explicitly named in the excerpts."""
    try:
        result = complete_json(SYSTEM_BASE, prompt)
        return result if isinstance(result, list) else []
    except LLMError:
        return []


def extract_obligations(document_id: str) -> list[dict]:
    chunks = _gather_context(document_id, EXTRACTION_QUERIES["obligations"], top_k=12)
    if not chunks:
        return []
    prompt = f"""Document excerpts:
{_format_context(chunks)}

Extract concrete obligations each party has under this agreement.
Return a JSON array: [{{"party_name": str, "obligation_text": str, "chunk_id": str, "page_number": int}}]
Only extract obligations explicitly stated in the excerpts. Keep obligation_text concise (one sentence)."""
    try:
        result = complete_json(SYSTEM_BASE, prompt)
        return result if isinstance(result, list) else []
    except LLMError:
        return []


def extract_dates(document_id: str) -> list[dict]:
    chunks = _gather_context(document_id, EXTRACTION_QUERIES["dates"], top_k=12)
    if not chunks:
        return []
    prompt = f"""Document excerpts:
{_format_context(chunks)}

Extract important dates, deadlines, and time periods (start date, end date, renewal date,
payment schedule, notice periods, deadlines).
Return a JSON array: [{{"label": str, "date_value": str, "description": str, "chunk_id": str, "page_number": int}}]
"date_value" can be a specific date or a duration (e.g. "30 days") if that's what the document states.
Only include what is explicitly stated."""
    try:
        result = complete_json(SYSTEM_BASE, prompt)
        return result if isinstance(result, list) else []
    except LLMError:
        return []


CLAUSE_CATEGORIES = [
    "Termination", "Payment", "Confidentiality", "Liability", "Indemnification",
    "Intellectual Property", "Non-compete", "Dispute Resolution", "Governing Law",
    "Renewal", "Penalties",
]


def extract_clauses(document_id: str) -> list[dict]:
    chunks = _gather_context(document_id, EXTRACTION_QUERIES["clauses"], top_k=16)
    if not chunks:
        return []
    prompt = f"""Document excerpts:
{_format_context(chunks)}

Identify which of these clause categories appear in the excerpts: {", ".join(CLAUSE_CATEGORIES)}.
For each category that is present, return a JSON array item:
{{"category": str, "title": str, "original_text": str, "plain_explanation": str, "chunk_id": str, "page_number": int}}

Rules:
- "original_text" must be copied/quoted closely from the excerpt (trim to the relevant sentence(s), max ~50 words).
- "plain_explanation" must translate the legal language into plain English, preserving its actual meaning.
  Do not add legal conclusions beyond what the clause literally says.
- Only include categories that actually appear in the excerpts. Skip categories with no textual support.
Return a JSON array."""
    try:
        result = complete_json(SYSTEM_BASE, prompt, max_tokens=3000)
        return result if isinstance(result, list) else []
    except LLMError:
        return []
