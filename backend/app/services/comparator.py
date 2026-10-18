"""
Contract comparison.

Compares two analyzed documents using their extracted clauses (structured
matching by category) plus word-level text diffs, and summarizes changes in
payment terms, deadlines, liability/indemnity, termination/renewal and risk
profile. Every diff line references real stored text — nothing is invented,
and the summary explicitly avoids claiming that every change is legally
significant.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app import models
from app.services.llm import complete_json, LLMError

_WORD_RE = re.compile(r"\S+\s*")
_AMOUNT_RE = re.compile(
    r"(?:[$€£]\s?|USD\s|EUR\s|GBP\s)\s?\d[\d,]*(?:\.\d{1,2})?"
)
_DAYS_RE = re.compile(r"\b\d{1,4}\s+(?:calendar\s+|business\s+)?days?\b", re.IGNORECASE)

CHANGE_TYPES = ("added", "removed", "modified", "unchanged", "similar")


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text or "")


def word_diff(a_text: str, b_text: str) -> dict:
    """Word-level diff with positions so the UI can highlight changes."""
    a_tokens, b_tokens = _tokenize(a_text), _tokenize(b_text)
    sm = SequenceMatcher(None, a_tokens, b_tokens, autojunk=False)
    changes: list[dict] = []
    identical = True
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            identical = False
        changes.append({
            "type": tag,  # equal | delete | insert | replace
            "a_start": i1, "a_end": i2,
            "b_start": j1, "b_end": j2,
        })
    ratio = sm.ratio()
    return {
        "a_tokens": a_tokens,
        "b_tokens": b_tokens,
        "opcodes": changes,
        "similarity": round(ratio, 3),
        "identical": identical,
    }


def _classify_change(similarity: float, a_present: bool, b_present: bool) -> str:
    if a_present and not b_present:
        return "removed"
    if b_present and not a_present:
        return "added"
    if similarity >= 0.97:
        return "unchanged"
    if similarity >= 0.70:
        return "similar"
    return "modified"


def _key_values(text: str) -> dict:
    return {
        "amounts": sorted({m.group(0).strip() for m in _AMOUNT_RE.finditer(text or "")}),
        "day_terms": sorted({re.sub(r"\s+", " ", m.group(0).lower()) for m in _DAYS_RE.finditer(text or "")}),
    }


def compare_documents(db: Session, doc_a: models.Document, doc_b: models.Document) -> dict:
    """Builds a structured comparison between two analyzed documents."""
    clauses_a = db.query(models.Clause).filter(models.Clause.document_id == doc_a.id).all()
    clauses_b = db.query(models.Clause).filter(models.Clause.document_id == doc_b.id).all()
    risks_a = db.query(models.Risk).filter(models.Risk.document_id == doc_a.id).all()
    risks_b = db.query(models.Risk).filter(models.Risk.document_id == doc_b.id).all()

    by_cat_a: dict[str, list] = {}
    by_cat_b: dict[str, list] = {}
    for c in clauses_a:
        by_cat_a.setdefault((c.category or "Other").lower(), []).append(c)
    for c in clauses_b:
        by_cat_b.setdefault((c.category or "Other").lower(), []).append(c)

    clause_diffs: list[dict] = []
    categories = sorted(set(by_cat_a) | set(by_cat_b))

    for cat in categories:
        list_a = by_cat_a.get(cat, [])
        list_b = by_cat_b.get(cat, [])
        count = max(len(list_a), len(list_b))
        for i in range(count):
            ca = list_a[i] if i < len(list_a) else None
            cb = list_b[i] if i < len(list_b) else None
            text_a = (ca.original_text if ca else "") or ""
            text_b = (cb.original_text if cb else "") or ""
            diff = word_diff(text_a, text_b) if (ca and cb) else None
            similarity = diff["similarity"] if diff else 0.0
            change = _classify_change(similarity, ca is not None, cb is not None)
            key_a = _key_values(text_a)
            key_b = _key_values(text_b)
            # Material term changes (amounts, day terms) are "modified" even when
            # the surrounding wording is nearly identical — a payment clause going
            # from $10,000/30 days to $25,000/60 days is the whole point of a
            # comparison, not a cosmetic similarity.
            if change in ("unchanged", "similar") and (
                key_a["amounts"] != key_b["amounts"] or key_a["day_terms"] != key_b["day_terms"]
            ):
                change = "modified"
            entry = {
                "category": cat,
                "change": change,
                "clause_a": _clause_ref(ca),
                "clause_b": _clause_ref(cb),
                "similarity": similarity,
                "diff": diff,
                "key_values_a": key_a,
                "key_values_b": key_b,
            }
            if change not in ("unchanged",):
                clause_diffs.append(entry)

    # --- Risk profile delta ---
    cats_a = {(r.category or "other") for r in risks_a}
    cats_b = {(r.category or "other") for r in risks_b}
    levels_a = [r.level for r in risks_a]
    levels_b = [r.level for r in risks_b]
    risk_delta = {
        "categories_added": sorted(cats_b - cats_a),
        "categories_removed": sorted(cats_a - cats_b),
        "overall_level_a": _level_from(levels_a),
        "overall_level_b": _level_from(levels_b),
        "high_count_a": levels_a.count("High"),
        "high_count_b": levels_b.count("High"),
        "new_findings": [
            {"title": r.title, "category": r.category, "level": r.level, "page_number": r.page_number}
            for r in risks_b if (r.category or "other") not in cats_a
        ],
    }

    result = {
        "document_a": {"id": doc_a.id, "filename": doc_a.filename, "document_type": doc_a.document_type},
        "document_b": {"id": doc_b.id, "filename": doc_b.filename, "document_type": doc_b.document_type},
        "clause_changes": clause_diffs,
        "risk_delta": risk_delta,
        "summary": None,
        "summary_disclaimer": (
            "This comparison highlights textual differences. Whether a change is "
            "legally significant depends on your circumstances — consult a qualified "
            "professional for legal judgment."
        ),
    }
    result["summary"] = _llm_summary(result)
    return result


def _level_from(levels: list[str]) -> str:
    if "High" in levels:
        return "High"
    if "Medium" in levels:
        return "Medium"
    if "Low" in levels:
        return "Low"
    return "Unknown"


def _clause_ref(clause) -> dict | None:
    if clause is None:
        return None
    return {
        "id": clause.id,
        "category": clause.category,
        "title": clause.title,
        "original_text": clause.original_text,
        "page_number": clause.page_number,
        "section_reference": clause.section_reference,
        "verification_status": clause.verification_status,
    }


def _llm_summary(result: dict) -> str | None:
    """Short grounded summary of the comparison. Best-effort; never blocks."""
    lines = []
    for change in result["clause_changes"][:12]:
        cat = change["category"]
        if change["change"] == "added":
            lines.append(f"- {cat}: present in the SECOND document only")
        elif change["change"] == "removed":
            lines.append(f"- {cat}: present in the FIRST document only")
        else:
            a_text = (change["clause_a"] or {}).get("original_text") or ""
            b_text = (change["clause_b"] or {}).get("original_text") or ""
            lines.append(f"- {cat} FIRST: {a_text[:300]}\n  {cat} SECOND: {b_text[:300]}")
    if not lines:
        return "No clause-level differences were detected between the two documents."
    delta = result["risk_delta"]
    prompt = f"""You are comparing two versions of a contract for LexClarity.

Key clause differences:
{chr(10).join(lines)}

Risk profile: first document overall level {delta['overall_level_a']} ({delta['high_count_a']} high-severity findings); second document {delta['overall_level_b']} ({delta['high_count_b']} high-severity findings).
New risk categories in the second document: {', '.join(delta['categories_added']) or 'none'}.

Write a concise 3-5 sentence plain-English summary of the most important changes.
Describe what changed textually; do NOT declare the changes legally significant.
Be factual and hedge where the text is ambiguous."""
    try:
        text = complete_json(
            "You summarize contract comparisons factually and concisely. JSON: {\"summary\": str}",
            prompt,
            max_tokens=600,
        )
        if isinstance(text, dict) and text.get("summary"):
            return str(text["summary"])[:1500]
    except LLMError:
        pass
    return (
        f"{len(result['clause_changes'])} clause-level differences were detected. "
        f"Overall risk moved from {delta['overall_level_a']} to {delta['overall_level_b']}. "
        "Review the highlighted differences below."
    )
