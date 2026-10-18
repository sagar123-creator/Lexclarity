"""
Structured extraction: entities, obligations, dates, and key clauses.

Strategy: rather than sending the whole document to the LLM in one shot
(expensive, lossy, and prone to hallucination on long documents), we use the
already-chunked, embedded text and retrieve the chunks most relevant to each
extraction target via semantic search, then ask the LLM to extract
structured JSON grounded ONLY in those chunks, always carrying page/section
metadata through so every extracted item can cite its source.

Every extracted item carries an exact quotation which is then validated
against its cited source chunk (services/evidence.py); items whose quote
cannot be located are flagged rather than trusted.
"""
from app.services.embeddings import embed_query
from app.services.vector_store import get_vector_store
from app.services.llm import complete_json
from app.services.evidence import validate_finding_citation

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


def _gather_context(document_id: str, query: str, top_k: int = 8) -> list[dict]:
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

QUOTE_RULE = (
    '- "quote" must be an EXACT verbatim quotation (max ~40 words) copied word-for-word '
    "from the excerpt identified by chunk_id. If you cannot quote it verbatim, omit the item."
)


def _validate_quote(db, document_id: str, chunk_id: str | None, quote: str | None) -> dict:
    verified, start, end, note = validate_finding_citation(db, document_id, chunk_id, quote)
    return {
        "quote_verified": verified if quote else None,
        "char_start": start,
        "char_end": end,
        "quote_note": note if quote else None,
    }


def extract_entities(document_id: str) -> list[dict] | None:
    """Returns a list of entity dicts, or an empty list when none were found.

    LLM provider errors propagate as `LLMError` (with their reason) so the
    pipeline can record exactly why this section is missing."""
    chunks = _gather_context(document_id, EXTRACTION_QUERIES["entities"])
    if not chunks:
        return []
    prompt = f"""Document excerpts:
{_format_context(chunks)}

Extract every party/entity involved in this agreement (companies and individuals).
Return a JSON array of objects: [{{"name": str, "role": str, "entity_type": "organization"|"individual"}}]
"role" should be their role in the agreement (e.g. "Employer", "Tenant", "Service Provider").
Only include entities explicitly named in the excerpts."""
    result = complete_json(SYSTEM_BASE, prompt)
    return result if isinstance(result, list) else []


def extract_obligations(db, document_id: str) -> list[dict] | None:
    chunks = _gather_context(document_id, EXTRACTION_QUERIES["obligations"], top_k=8)
    if not chunks:
        return []
    prompt = f"""Document excerpts:
{_format_context(chunks)}

Extract concrete obligations each party has under this agreement.
Return a JSON array:
[{{"party_name": str, "obligation_text": str, "deadline_text": str|null,
   "trigger_event": str|null, "conditions": str|null,
   "quote": str, "chunk_id": str, "page_number": int}}]
Rules:
- Only extract obligations explicitly stated in the excerpts. Keep obligation_text concise (one sentence).
- "deadline_text" is the stated time limit if one exists (e.g. "within 30 days"), else null.
- "trigger_event" is what sets the obligation running (e.g. "upon written notice"), else null.
- "conditions" lists any conditions/exceptions attached to the obligation, else null.
{QUOTE_RULE}"""
    result = complete_json(SYSTEM_BASE, prompt, max_tokens=3500)
    items = result if isinstance(result, list) else []
    enriched = []
    for o in items:
        if not isinstance(o, dict):
            continue
        chunk_id = o.get("chunk_id")
        v = _validate_quote(db, document_id, chunk_id, o.get("quote"))
        o.update(v)
        if o.get("quote") and not o["quote_verified"]:
            o["verification_status"] = "needs_review"
        else:
            o["verification_status"] = "supported" if o.get("quote") else "unverified"
        enriched.append(o)
    return enriched


def extract_dates(db, document_id: str) -> list[dict] | None:
    chunks = _gather_context(document_id, EXTRACTION_QUERIES["dates"], top_k=8)
    if not chunks:
        return []
    prompt = f"""Document excerpts:
{_format_context(chunks)}

Extract important dates, deadlines, and time periods (start date, end date, renewal date,
payment schedule, notice periods, deadlines).
Return a JSON array:
[{{"label": str, "date_value": str, "description": str, "quote": str, "chunk_id": str, "page_number": int}}]
Rules:
- "date_value" can be a specific date or a duration (e.g. "30 days") if that's what the document states.
- Only include what is explicitly stated.
{QUOTE_RULE}"""
    result = complete_json(SYSTEM_BASE, prompt, max_tokens=3500)
    items = result if isinstance(result, list) else []
    enriched = []
    for d in items:
        if not isinstance(d, dict):
            continue
        chunk_id = d.get("chunk_id")
        v = _validate_quote(db, document_id, chunk_id, d.get("quote"))
        d.update(v)
        if d.get("quote") and not d["quote_verified"]:
            d["verification_status"] = "needs_review"
        else:
            d["verification_status"] = "supported" if d.get("quote") else "unverified"
        enriched.append(d)
    return enriched


CLAUSE_CATEGORIES = [
    "Termination", "Payment", "Confidentiality", "Liability", "Indemnification",
    "Intellectual Property", "Non-compete", "Dispute Resolution", "Governing Law",
    "Renewal", "Penalties",
]


def extract_clauses(db, document_id: str) -> list[dict] | None:
    chunks = _gather_context(document_id, EXTRACTION_QUERIES["clauses"], top_k=8)
    if not chunks:
        return []
    prompt = f"""Document excerpts:
{_format_context(chunks)}

Identify which of these clause categories appear in the excerpts: {", ".join(CLAUSE_CATEGORIES)}.
For each category that is present, return a JSON array item:
{{"category": str, "title": str, "original_text": str, "plain_explanation": str,
  "parties": [str], "rights_obligations": str, "concerns": str|null,
  "chunk_id": str, "page_number": int}}

Rules:
- "original_text" must be copied/quoted closely from the excerpt (trim to the relevant sentence(s), max ~50 words).
- "plain_explanation" must translate the legal language into plain English, preserving its actual meaning.
  Do not add legal conclusions beyond what the clause literally says.
- "parties" lists the parties whose rights or obligations this clause governs (e.g. ["Service Provider"]).
- "rights_obligations" states, in plain English, what each party is entitled to or must do under the clause.
- "concerns" notes any potential concerns in hedged language ("may warrant review"), or null.
- Only include categories that actually appear in the excerpts. Skip categories with no textual support.
{QUOTE_RULE}
Return a JSON array."""
    result = complete_json(SYSTEM_BASE, prompt, max_tokens=4000)
    items = result if isinstance(result, list) else []
    enriched = []
    for c in items:
        if not isinstance(c, dict):
            continue
        chunk_id = c.get("chunk_id")
        # original_text doubles as the evidence quote
        v = _validate_quote(db, document_id, chunk_id, c.get("original_text"))
        c.update(v)
        if c.get("original_text") and not c["quote_verified"]:
            c["verification_status"] = "needs_review"
        else:
            c["verification_status"] = "supported" if c.get("original_text") else "unverified"
        enriched.append(c)
    return enriched
