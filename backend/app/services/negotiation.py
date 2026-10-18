"""
Contract Negotiation Assistant.

Given a clause, produce a negotiation suggestion: the original wording, a
plain-English explanation, the concern to discuss, a proposed alternative
wording, the rationale, and concrete negotiation points/questions — plus a
word-level comparison of original vs proposed text.

Proposed clauses are AI-generated suggestions. They are never presented as
legally valid, enforceable, or suitable in every jurisdiction.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import models
from app.services.llm import complete_json, LLMError
from app.services.comparator import word_diff

_SYSTEM = (
    "You are LexClarity's negotiation assistant. You draft alternative clause "
    "wording as a SUGGESTION for the user to discuss with their counterparty "
    "and their lawyer. You are not a lawyer; you never claim proposed wording "
    "is legally valid, enforceable, or suitable in every jurisdiction. You only "
    "work from the clause text provided — you never invent facts about the deal."
)


def suggest_negotiation(db: Session, document: models.Document, clause: models.Clause) -> dict:
    """Generate and persist a negotiation suggestion for one clause."""
    original = clause.original_text or ""
    if not original.strip():
        raise ValueError("This clause has no original text to negotiate from.")

    parties = ", ".join(clause.parties or []) or "the parties"
    prompt = f"""Clause from {document.filename} (category: {clause.category}):

VERBATIM ORIGINAL WORDING:
\"\"\"{original}\"\"\"

Plain-English explanation of the clause: {clause.plain_explanation or "(not available)"}
Parties it governs: {parties}
Potential concerns noted in analysis: {clause.concerns or "(none noted)"}

Produce a negotiation suggestion as JSON:
{{
  "concern": "the specific concern to raise, in plain English (hedged, non-definitive)",
  "proposed_text": "alternative clause wording as an AI SUGGESTION — drafted to be workable and balanced, using [PLACEHOLDER: ...] for any deal-specific fact you don't have",
  "rationale": "why this revision may be worth proposing",
  "negotiation_points": ["3-6 concrete points or questions to raise with the counterparty"]
}}
Rules:
- The proposed wording must be a full, self-contained clause replacement.
- Do not claim the proposal is legally enforceable.
- Use placeholders for any missing deal specifics (amounts, dates, party names)."""

    try:
        result = complete_json(_SYSTEM, prompt, max_tokens=2000)
    except LLMError as e:
        raise ValueError(f"Negotiation suggestion failed: {e}") from e

    if not isinstance(result, dict) or not result.get("proposed_text"):
        raise ValueError("The model did not return a usable suggestion. Please try again.")

    proposed = str(result["proposed_text"]).strip()
    suggestion = models.ClauseSuggestion(
        document_id=document.id,
        clause_id=clause.id,
        original_text=original,
        plain_explanation=clause.plain_explanation,
        concern=str(result.get("concern") or "") or None,
        proposed_text=proposed,
        rationale=str(result.get("rationale") or "") or None,
        negotiation_points=result.get("negotiation_points") if isinstance(result.get("negotiation_points"), list) else [],
        diff=word_diff(original, proposed),
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    return suggestion
