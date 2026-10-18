"""
Missing-clause detector — document-type-specific review checklists.

For a given document type, each checklist item is checked against the
document via semantic retrieval plus a bounded LLM check, producing one of:
  detected | not_detected | unclear | not_applicable

This is a PRELIMINARY document review to help users spot clauses that may be
worth discussing — it is not a determination that a contract is legally
complete or incomplete. Document silence never proves a clause is legally
required or absent from the parties' actual obligations.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.embeddings import embed_query
from app.services.vector_store import get_vector_store
from app.services.llm import complete_json, LLMError
from app.services.evidence import find_quote

DETECTED = "detected"
NOT_DETECTED = "not_detected"
UNCLEAR = "unclear"
NOT_APPLICABLE = "not_applicable"


@dataclass
class ChecklistItem:
    key: str
    label: str
    description: str


CHECKLISTS: dict[str, list[ChecklistItem]] = {
    "NDA": [
        ChecklistItem("definition", "Confidentiality definition", "Defines what counts as confidential information"),
        ChecklistItem("obligations", "Confidentiality obligations", "What the receiving party must do with the information"),
        ChecklistItem("exceptions", "Standard exceptions", "Public knowledge, independent development, prior possession"),
        ChecklistItem("permitted_disclosures", "Permitted/required disclosures", "Disclosures required by law or to advisors"),
        ChecklistItem("duration", "Duration of confidentiality", "How long the obligations last, including survival"),
        ChecklistItem("return_destruction", "Return or destruction of information", "What happens to materials when the agreement ends"),
        ChecklistItem("remedies", "Remedies for breach", "Injunctive relief or damages for breach"),
        ChecklistItem("governing_law", "Governing law", "Which jurisdiction's law applies"),
    ],
    "Employment Agreement": [
        ChecklistItem("compensation", "Compensation and benefits", "Salary, bonus, benefits terms"),
        ChecklistItem("duties", "Job duties and scope", "Role, responsibilities, changes to role"),
        ChecklistItem("term", "Term and termination", "Duration, notice periods, termination for cause"),
        ChecklistItem("ip_assignment", "Intellectual property assignment", "Who owns work created during employment"),
        ChecklistItem("confidentiality", "Confidentiality", "Protection of employer and third-party information"),
        ChecklistItem("non_compete", "Non-compete / non-solicitation", "Restrictions after employment ends"),
        ChecklistItem("benefits_leave", "Benefits and leave", "Health, retirement, leave entitlements"),
        ChecklistItem("dispute_resolution", "Dispute resolution", "Arbitration, venue, governing law"),
    ],
    "Service Agreement": [
        ChecklistItem("scope", "Scope of services", "What will be delivered"),
        ChecklistItem("payment", "Payment terms", "Amounts, schedule, late payment"),
        ChecklistItem("term_termination", "Term and termination", "Duration, notice, termination rights"),
        ChecklistItem("liability", "Limitation of liability", "Caps and exclusions of damages"),
        ChecklistItem("indemnification", "Indemnification", "Who covers third-party claims"),
        ChecklistItem("confidentiality", "Confidentiality", "Protection of information shared under the agreement"),
        ChecklistItem("ip", "Intellectual property", "Ownership of deliverables and pre-existing IP"),
        ChecklistItem("insurance", "Insurance requirements", "Required coverage"),
        ChecklistItem("dispute_resolution", "Dispute resolution and governing law", "Arbitration, venue, law"),
    ],
    "Rental Agreement": [
        ChecklistItem("rent", "Rent amount and payment schedule", "How much and when"),
        ChecklistItem("deposit", "Security deposit", "Amount, handling, return conditions"),
        ChecklistItem("term", "Term and renewal", "Lease duration and renewal terms"),
        ChecklistItem("maintenance", "Maintenance and repairs", "Responsibilities of each party"),
        ChecklistItem("use", "Permitted use", "How the property may be used"),
        ChecklistItem("termination", "Termination and eviction", "Notice and grounds for ending the tenancy"),
        ChecklistItem("insurance", "Insurance", "Required coverage for either party"),
        ChecklistItem("disputes", "Dispute resolution", "Venue and governing law"),
    ],
    "Purchase Agreement": [
        ChecklistItem("goods", "Description of goods/services", "What is being purchased"),
        ChecklistItem("price_payment", "Price and payment terms", "Amount, currency, schedule"),
        ChecklistItem("delivery", "Delivery and acceptance", "Timelines, inspection, rejection"),
        ChecklistItem("warranties", "Warranties", "Quality guarantees and disclaimers"),
        ChecklistItem("title_risk", "Title and risk of loss", "When ownership and risk transfer"),
        ChecklistItem("liability", "Limitation of liability", "Caps and exclusions"),
        ChecklistItem("termination", "Termination", "Rights to end the agreement"),
        ChecklistItem("dispute_resolution", "Dispute resolution and governing law", "Arbitration, venue, law"),
    ],
    "Loan Agreement": [
        ChecklistItem("principal", "Principal amount and disbursement", "How much is lent and how it is provided"),
        ChecklistItem("interest", "Interest rate", "Rate, fixed or variable, calculation"),
        ChecklistItem("repayment", "Repayment schedule", "When and how payments are made"),
        ChecklistItem("collateral", "Collateral/security", "What secures the loan"),
        ChecklistItem("events_default", "Events of default", "What triggers default"),
        ChecklistItem("remedies", "Lender remedies", "What the lender can do on default"),
        ChecklistItem("prepayment", "Prepayment terms", "Early repayment conditions"),
        ChecklistItem("governing_law", "Governing law and jurisdiction", "Law and venue"),
    ],
    "Partnership Agreement": [
        ChecklistItem("capital", "Capital contributions", "What each partner contributes"),
        ChecklistItem("profit_sharing", "Profit and loss sharing", "How profits and losses are divided"),
        ChecklistItem("management", "Management and voting", "Decision-making authority"),
        ChecklistItem("duties", "Partner duties", "What each partner must do"),
        ChecklistItem("term", "Term and dissolution", "How the partnership ends"),
        ChecklistItem("exit", "Transfer of interests / buyout", "What happens when a partner leaves"),
        ChecklistItem("confidentiality", "Confidentiality", "Protection of partnership information"),
        ChecklistItem("dispute_resolution", "Dispute resolution", "Arbitration, venue, governing law"),
    ],
    "Other": [
        ChecklistItem("parties_scope", "Parties and scope", "Who is bound and what the agreement covers"),
        ChecklistItem("payment", "Payment terms", "Amounts, schedule, late payment"),
        ChecklistItem("term_termination", "Term and termination", "Duration, notice, termination rights"),
        ChecklistItem("liability", "Liability", "Limits on liability and remedies"),
        ChecklistItem("confidentiality", "Confidentiality", "Protection of information"),
        ChecklistItem("ip", "Intellectual property", "Ownership of work product"),
        ChecklistItem("dispute_resolution", "Dispute resolution and governing law", "Arbitration, venue, law"),
    ],
}

_SIMILARITY_THRESHOLD = 0.30


def checklist_for(document_type: str | None) -> tuple[str, list[ChecklistItem]]:
    if document_type and document_type in CHECKLISTS:
        return document_type, CHECKLISTS[document_type]
    return "Other", CHECKLISTS["Other"]


_SYSTEM = (
    "You are LexClarity's preliminary clause-review engine. You check whether a "
    "specific clause appears in the provided document excerpts. You never assume "
    "a clause is legally required, and you never claim a document is legally "
    "incomplete. Base every answer strictly on the excerpts."
)


def run_checklist(document_id: str, document_type: str | None) -> list[dict]:
    """Returns one result dict per checklist item for the document type."""
    checklist_name, items = checklist_for(document_type)
    store = get_vector_store()

    results: list[dict] = []
    for item in items:
        query_emb = embed_query(
            f"{item.label}: {item.description} clause terms conditions"
        )
        retrieved = store.query(document_id, query_emb, top_k=3)
        best = retrieved[0] if retrieved else None

        if best is None or best.similarity < _SIMILARITY_THRESHOLD:
            results.append({
                "checklist_type": checklist_name,
                "item_key": item.key,
                "item_label": item.label,
                "state": NOT_DETECTED,
                "explanation": (
                    "No passage in the document was similar enough to this clause topic "
                    f"(best similarity {best.similarity:.2f} of the required {_SIMILARITY_THRESHOLD})."
                    if best else "No passages were available to compare against."
                ),
                "evidence_quote": None,
                "page_number": None,
                "chunk_id": None,
            })
            continue

        context = "\n\n".join(
            f"[chunk_id={r.chunk_id} page={r.page_number}]\n{r.text}" for r in retrieved
        )
        prompt = f"""Document excerpts:
{context}

Checklist item: {item.label} — {item.description}

Decide whether this checklist item is addressed in the excerpts.
Return ONLY a JSON object:
{{
  "state": "detected" | "not_detected" | "unclear" | "not_applicable",
  "explanation": "one sentence grounded in the excerpts",
  "quote": "an EXACT verbatim quotation (max ~30 words) supporting the state, or null",
  "chunk_id": "chunk_id the quote comes from, or null"
}}
- Use "unclear" when related text exists but doesn't clearly address the item.
- Use "not_applicable" when the excerpts show this concept doesn't apply to this arrangement.
- Never invent text."""
        try:
            out = complete_json(_SYSTEM, prompt, max_tokens=400)
        except LLMError:
            out = None

        state, explanation, quote, chunk_id = UNCLEAR, "The checker could not be completed (LLM error).", None, None
        if isinstance(out, dict):
            s = str(out.get("state", "")).lower()
            state = s if s in (DETECTED, NOT_DETECTED, UNCLEAR, NOT_APPLICABLE) else UNCLEAR
            explanation = str(out.get("explanation") or "")[:500]
            quote = out.get("quote")
            chunk_id = out.get("chunk_id")

        # Validate quote against the cited chunk; drop it if not found.
        page_number = None
        if quote and chunk_id:
            chunk = next((r for r in retrieved if r.chunk_id == chunk_id), None)
            if chunk and find_quote(quote, chunk.text).found:
                page_number = chunk.page_number
            else:
                quote, chunk_id = None, None
                explanation += " (The supporting quotation could not be verified in the source text.)"

        results.append({
            "checklist_type": checklist_name,
            "item_key": item.key,
            "item_label": item.label,
            "state": state,
            "explanation": explanation,
            "evidence_quote": quote,
            "page_number": page_number,
            "chunk_id": chunk_id,
        })
    return results
