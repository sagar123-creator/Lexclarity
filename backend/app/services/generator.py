"""
Legal Document Generator — grounded drafting workflows.

Templates produce editable drafts (negotiation emails, clarification
requests, renewal emails, clause-revision requests, formal correspondence,
counter-proposals, and lawyer/stakeholder summaries) grounded strictly in
the selected document findings.

Rules enforced here:
- The prompt contains only real stored text (findings + quotations).
- The model must use [PLACEHOLDER: ...] for any fact it does not have
  (names, addresses, exact dates not in the document, etc.).
- Output is stored as a Draft the user can edit; nothing is ever sent
  anywhere, and drafts are clearly labeled AI-generated until edited.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import models
from app.services.llm import complete_json, LLMError

# Canonical pattern lives on the model (it keeps Draft.placeholders in sync);
# re-exported here for existing callers.
PLACEHOLDER_RE = models.PLACEHOLDER_RE

TEMPLATE_KINDS: dict[str, dict] = {
    "negotiation_email": {
        "title": "Negotiation email",
        "description": "Email raising concerns from the analysis and proposing discussion points.",
    },
    "clarification_request": {
        "title": "Request for clarification",
        "description": "Formal request to the counterparty to clarify ambiguous terms.",
    },
    "renewal_email": {
        "title": "Contract renewal email",
        "description": "Email about renewal dates, notice windows and next steps.",
    },
    "clause_revision_request": {
        "title": "Request for clause revision",
        "description": "Specific request to revise one or more clauses, quoting the current wording.",
    },
    "formal_correspondence": {
        "title": "Formal correspondence",
        "description": "A formal letter referencing the agreement and specific findings.",
    },
    "counter_proposal": {
        "title": "Counter-proposal",
        "description": "Counter-proposal with alternative wording for selected clauses.",
    },
    "lawyer_summary": {
        "title": "Summary for a lawyer or stakeholder",
        "description": "Structured brief of findings, evidence and open questions for professional review.",
    },
}

_SYSTEM = (
    "You are LexClarity's drafting assistant. You draft correspondence grounded "
    "STRICTLY in the provided document findings and quotations. You never invent "
    "facts, names, dates, amounts, legal references or contractual obligations. "
    "When a required fact is not provided, insert a clearly marked placeholder "
    "in the exact form [PLACEHOLDER: description] (e.g. [PLACEHOLDER: recipient "
    "name]). Keep quotes verbatim. The draft is a suggestion for the user to "
    "review and edit — LexClarity never sends anything on the user's behalf."
)


@dataclass
class FindingContext:
    label: str
    text: str
    quote: str | None = None
    page_number: int | None = None
    source_id: str | None = None


def gather_findings(db: Session, document_id: str, source_ids: list[str] | None) -> list[FindingContext]:
    """Collect the user-selected findings (risks, clauses, obligations, dates)
    that the draft must be grounded in."""
    out: list[FindingContext] = []
    risks = db.query(models.Risk).filter(models.Risk.document_id == document_id)
    clauses = db.query(models.Clause).filter(models.Clause.document_id == document_id)
    obligations = db.query(models.Obligation).filter(models.Obligation.document_id == document_id)
    dates = db.query(models.ImportantDate).filter(models.ImportantDate.document_id == document_id)

    def wanted(item_id: str | None) -> bool:
        return source_ids is None or (item_id is not None and item_id in source_ids)

    for r in risks.all():
        if wanted(r.id):
            out.append(FindingContext(
                label=f"Risk ({r.level}): {r.title}",
                text=f"{r.description} Why it matters: {r.why_it_matters}",
                quote=r.evidence_quote or None,
                page_number=r.page_number,
                source_id=r.id,
            ))
    for c in clauses.all():
        if wanted(c.id):
            out.append(FindingContext(
                label=f"Clause ({c.category}): {c.title}",
                text=c.plain_explanation or "",
                quote=c.original_text,
                page_number=c.page_number,
                source_id=c.id,
            ))
    for o in obligations.all():
        if wanted(o.id):
            out.append(FindingContext(
                label=f"Obligation of {o.party_name}",
                text=o.obligation_text,
                quote=o.evidence_quote,
                page_number=o.page_number,
                source_id=o.id,
            ))
    for d in dates.all():
        if wanted(d.id):
            out.append(FindingContext(
                label=f"Date: {d.label}",
                text=f"{d.date_value or ''} {d.description or ''}".strip(),
                quote=d.evidence_quote,
                page_number=d.page_number,
                source_id=d.id,
            ))
    return out


def _render_context(findings: list[FindingContext]) -> str:
    blocks = []
    for f in findings:
        block = f"### {f.label}"
        if f.text:
            block += f"\nAnalysis: {f.text}"
        if f.quote:
            block += f'\nDocument quotation (verbatim): "{f.quote}"'
        if f.page_number:
            block += f"\nSource: page {f.page_number}"
        blocks.append(block)
    return "\n\n".join(blocks) or "(no specific findings selected — draft a general message)"


def generate_draft(
    db: Session,
    document: models.Document,
    kind: str,
    source_ids: list[str] | None = None,
    user_instructions: str | None = None,
) -> dict:
    """Generate a grounded draft. Returns the draft payload (not yet saved)."""
    if kind not in TEMPLATE_KINDS:
        raise ValueError(f"Unknown template kind: {kind}")

    findings = gather_findings(db, document.id, source_ids)[:12]  # bound prompt size
    party_names = ", ".join(e.name for e in db.query(models.Entity).filter(models.Entity.document_id == document.id).all()) or "[PLACEHOLDER: party names]"

    instructions = {
        "negotiation_email": (
            "Write a professional email to the counterparty raising the selected concerns "
            "and proposing to discuss them. Reference the quoted clauses accurately. "
            "Tone: collaborative, firm, non-accusatory. Include a clear ask."
        ),
        "clarification_request": (
            "Write a concise email asking the counterparty to clarify the selected points. "
            "Quote the ambiguous wording verbatim and list specific questions."
        ),
        "renewal_email": (
            "Write an email about the contract's renewal/notice timeline based on the selected "
            "date findings, confirming the key dates and asking for confirmation of next steps."
        ),
        "clause_revision_request": (
            "Write a focused email requesting revision of the selected clauses. Quote the current "
            "wording verbatim, explain the concern in plain English, and ask to discuss alternatives."
        ),
        "formal_correspondence": (
            "Write a formal letter referencing the agreement and the selected findings. "
            "Use a professional letter format with placeholders for addresses."
        ),
        "counter_proposal": (
            "Write a counter-proposal email. For each selected clause, state the current "
            "wording (verbatim quote) and propose to discuss alternative terms — do NOT draft "
            "specific replacement legal language here (that is done in the Negotiation Assistant)."
        ),
        "lawyer_summary": (
            "Write a structured brief for a lawyer or business stakeholder: 1) Document overview, "
            "2) Key findings with verbatim quotes and page references, 3) Open questions, "
            "4) Suggested next steps. Neutral, factual, hedged where appropriate."
        ),
    }[kind]

    prompt = f"""Document: {document.filename} (type: {document.document_type or 'unknown'}).
Parties mentioned: {party_names}

Findings to ground the draft in:
{_render_context(findings)}

Instructions: {instructions}
{f"User's additional instructions: {user_instructions}" if user_instructions else ""}

Write the draft now.
Rules:
- Use ONLY the facts and quotations above. Never invent facts, names, dates, amounts or legal references.
- Use [PLACEHOLDER: ...] for any missing required information.
- Keep all document quotations verbatim.
- Do not claim the draft is legally sufficient; it is a starting point for the user to review."""

    try:
        result = complete_json(
            _SYSTEM + ' Respond with ONLY a JSON object: {"title": str, "content": str}',
            prompt,
            max_tokens=2500,
        )
    except LLMError as e:
        raise ValueError(f"Draft generation failed: {e}") from e

    if not isinstance(result, dict) or not result.get("content"):
        raise ValueError("The model did not return a usable draft. Please try again.")

    content = str(result["content"]).strip()
    title = str(result.get("title") or TEMPLATE_KINDS[kind]["title"]).strip()[:200]
    placeholders = sorted(set(PLACEHOLDER_RE.findall(content)))

    source_refs = [
        {
            "label": f.label,
            "quote": f.quote,
            "page_number": f.page_number,
            "document_id": document.id,
            "source_id": f.source_id,
        }
        for f in findings if f.quote
    ]

    return {
        "kind": kind,
        "title": title,
        "content": content,
        "placeholders": placeholders,
        "source_refs": source_refs,
    }
