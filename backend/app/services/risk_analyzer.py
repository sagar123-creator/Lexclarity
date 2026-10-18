"""
Risk analysis (evidence-grounded, rubric-scored).

Flow:
  1. Retrieve the chunks most relevant to risk-bearing clause types.
  2. Ask the LLM to identify candidate concerns, classify each into one of
     the documented categories (services/risk_rules.py) and QUOTE the
     supporting text with its chunk_id.
  3. Validate every quote against the cited source chunk — quotes that can't
     be located are flagged "needs_review", never presented as facts.
  4. Assign severity with the deterministic rubric (never the LLM's level);
     record which rubric rules fired.
  5. Verify the finding's claim against its source passage with the Trust &
     Verification engine (deterministic value checks + configured verifier).

The overall risk level derives from the rubric-assigned severities.
"""
from app.services.embeddings import embed_query
from app.services.vector_store import get_vector_store, RetrievedChunk
from app.services.llm import complete_json
from app.services import risk_rules
from app.services.evidence import validate_finding_citation
from app.services.verification import Passage, verify_claim, NEEDS_REVIEW

RISK_QUERY = (
    "liability, indemnification, unlimited liability, penalties, termination for convenience, "
    "automatic renewal, non-compete restrictions, exclusive jurisdiction, waiver of rights, "
    "limitation of remedies, unilateral amendment, arbitration, confidentiality obligations"
)

SYSTEM_PROMPT = (
    "You are LexClarity's risk-analysis engine. You identify clauses that MAY be "
    "concerning for a party to this agreement, based strictly on the provided "
    "excerpts. You are not a lawyer and must never state legal conclusions with "
    "certainty. Use hedged language such as 'potential risk', 'may expose', "
    "'this clause may warrant legal review'. Never invent clauses that are not "
    "in the excerpts."
)


def _passage_for(chunk: RetrievedChunk, ocr_used: bool = False) -> Passage:
    return Passage(
        text=chunk.text,
        similarity=1.0,  # source chunk is the candidate evidence; claim similarity computed inside
        chunk_id=chunk.chunk_id,
        page_number=chunk.page_number,
        section_heading=chunk.section_heading,
        ocr_used=ocr_used,
    )


def analyze_risks(db, document_id: str, ocr_pages: set[int] | None = None) -> list[dict]:
    """Returns risk dicts enriched with category, severity rationale,
    verification status, evidence quotes and suggested actions.

    An empty list means the provider ran and found nothing concerning. LLM
    provider errors propagate as `LLMError` (carrying their reason) so the
    pipeline can record exactly why the Risks section is missing.

    `db` is the SQLAlchemy session used to validate each finding's quote
    against its cited source chunk.
    """
    ocr_pages = ocr_pages or set()
    store = get_vector_store()
    query_emb = embed_query(RISK_QUERY)
    retrieved = store.query(document_id, query_emb, top_k=8)
    if not retrieved:
        return []

    context = "\n\n".join(
        f"[chunk_id={r.chunk_id} page={r.page_number} section={r.section_heading or 'n/a'}]\n{r.text}"
        for r in retrieved
    )
    category_names = ", ".join(
        f'"{k}" ({v})' for k, v in risk_rules.RISK_CATEGORIES.items()
    )

    prompt = f"""Document excerpts:
{context}

Identify potential risks in these excerpts for the party who is likely on the receiving end
of the more burdensome obligations. For each risk found, return a JSON array item:

{{
  "category": one of the documented category keys: [{", ".join(risk_rules.RISK_CATEGORIES)}],
  "title": "short risk name, e.g. 'Unlimited Liability'",
  "affected_party": "the party the risk likely affects, e.g. 'Service Provider' (or null)",
  "description": "what the clause actually says, in plain terms",
  "why_it_matters": "why this could be a concern, using hedged/cautious language",
  "plain_explanation": "one more sentence of plain-English context if useful",
  "quote": "an EXACT verbatim quotation (max ~40 words) copied word-for-word from the excerpt",
  "chunk_id": "copied from the excerpt header",
  "page_number": int
}}

Documented category keys and meanings: {category_names}

Rules:
- The "quote" MUST be copied word-for-word from the excerpt your finding is based on.
  If you cannot quote it verbatim, do not include the finding.
- Never say something IS legally dangerous with certainty — always hedge ("potential risk",
  "may expose the party to...", "this clause may warrant legal review").
- Only flag risks with clear textual support in the excerpts.
- Do not assign your own severity level — severity is computed separately by documented criteria.
- If nothing concerning is found, return an empty array.
Return a JSON array only."""

    result = complete_json(SYSTEM_PROMPT, prompt, max_tokens=3500)
    raw_risks = result if isinstance(result, list) else []

    by_chunk = {r.chunk_id: r for r in retrieved}
    enriched: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for item in raw_risks:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "Potential risk").strip()
        description = str(item.get("description") or "").strip()
        why = str(item.get("why_it_matters") or "").strip()
        quote = str(item.get("quote") or "").strip()
        chunk_id = item.get("chunk_id")
        chunk = by_chunk.get(chunk_id)
        if chunk is None:
            # fall back: try to locate the quote in any retrieved chunk
            from app.services.evidence import find_quote
            for r in retrieved:
                if quote and find_quote(quote, r.text).found:
                    chunk = r
                    break
        if chunk is None:
            continue
        dedupe_key = (title.lower(), chunk.chunk_id)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        # 1. Category: trust the LLM label only if the taxonomy accepts it,
        #    else derive it; unknown → "other" + review flag.
        category = item.get("category")
        if category not in risk_rules.RISK_CATEGORIES:
            category = risk_rules.categorize_finding(title, description) or "other"
        category_unknown = category == "other" and risk_rules.categorize_finding(title, description) is None

        # 2. Evidence validation: quote must exist in the cited chunk.
        quote_verified, char_start, char_end, quote_note = validate_finding_citation(
            db, document_id, chunk.chunk_id, quote
        )

        # 3. Deterministic severity rubric.
        rubric = risk_rules.apply_severity_rubric(category, chunk.text, llm_level=None)

        # 4. Claim verification against the source passage.
        claim = f"{title}. {description}".strip()
        passage = _passage_for(chunk, ocr_used=chunk.page_number in ocr_pages)
        claim_result = verify_claim(claim, [passage])

        verification_status = claim_result.status
        notes = list(claim_result.notes)
        if category_unknown:
            verification_status = NEEDS_REVIEW
            notes.append("Risk category could not be determined from documented criteria.")
        if quote and not quote_verified:
            verification_status = NEEDS_REVIEW
            notes.append(f"Supporting quotation could not be verified in the source text: {quote_note}")
        elif quote_note:
            notes.append(quote_note)

        enriched.append({
            "level": rubric.level,
            "category": category,
            "title": title,
            "affected_party": item.get("affected_party") or None,
            "description": description,
            "why_it_matters": why,
            "plain_explanation": item.get("plain_explanation"),
            "quote": quote or None,
            "quote_verified": quote_verified if quote else None,
            "chunk_id": chunk.chunk_id,
            "page_number": chunk.page_number,
            "section": chunk.section_heading,
            "char_start": char_start,
            "char_end": char_end,
            "severity_rationale": rubric.rationale,
            "suggested_action": risk_rules.suggested_action_for(category),
            "verification_status": verification_status,
            "verification_explanation": claim_result.explanation,
            "verification_notes": notes,
        })

    return enriched


def overall_risk_level(risks: list[dict]) -> str:
    return risk_rules.overall_risk_level([r.get("level", "Low") for r in risks])
