"""
Risk analysis.

Retrieves the chunks most relevant to risk-bearing clause types (liability,
indemnification, termination, penalties, non-compete, IP assignment...) and
asks the LLM to flag potential concerns using cautious, non-definitive
language, each grounded in a specific source chunk/page.
"""
from app.services.embeddings import embed_query
from app.services.vector_store import get_vector_store
from app.services.llm import complete_json, LLMError

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


def analyze_risks(document_id: str) -> list[dict]:
    store = get_vector_store()
    query_emb = embed_query(RISK_QUERY)
    retrieved = store.query(document_id, query_emb, top_k=14)
    if not retrieved:
        return []

    context = "\n\n".join(
        f"[chunk_id={r.chunk_id} page={r.page_number} section={r.section_heading or 'n/a'}]\n{r.text}"
        for r in retrieved
    )

    prompt = f"""Document excerpts:
{context}

Identify potential risks in these excerpts for the party who is likely on the receiving end
of the more burdensome obligations. For each risk found, return a JSON array item:

{{
  "level": "High" | "Medium" | "Low",
  "title": "short risk name, e.g. 'Unlimited Liability'",
  "description": "what the clause actually says, in plain terms",
  "why_it_matters": "why this could be a concern, using hedged/cautious language",
  "plain_explanation": "one more sentence of plain-English context if useful",
  "chunk_id": "copied from the excerpt header",
  "page_number": int
}}

Rules:
- Never say something IS legally dangerous with certainty — always hedge ("potential risk", "may expose the party to...", "may warrant legal review").
- Only flag risks with clear textual support in the excerpts.
- If nothing concerning is found, return an empty array.
Return a JSON array only."""

    try:
        result = complete_json(SYSTEM_PROMPT, prompt, max_tokens=3000)
        return result if isinstance(result, list) else []
    except LLMError:
        return []


def overall_risk_level(risks: list[dict]) -> str:
    levels = {r.get("level") for r in risks}
    if "High" in levels:
        return "High"
    if "Medium" in levels:
        return "Medium"
    if "Low" in levels:
        return "Low"
    return "Unknown"
