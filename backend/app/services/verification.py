"""
Trust & Verification Engine.

Verifies individual claims made by the system against the retrieved source
passages it was grounded in. Verification combines:

1. Deterministic value checks — dates, currency amounts, percentages and
   day-counts mentioned in a claim must actually appear in the evidence;
   a mismatch is treated as a contradiction.
2. Semantic entailment — a configurable verifier:
   - "nli": a local NLI model (transformers), or
   - "llm": the configured LLM used strictly as a textual-entailment judge
     (explicitly NOT treated as proof), or
   - "off"/"unavailable": semantic checks are skipped and claims that can't
     be established deterministically are reported as insufficient.

Statuses returned per claim:
  supported      — evidence entails the claim (and no deterministic conflict)
  contradicted   — evidence conflicts with the claim
  insufficient   — evidence neither supports nor contradicts
  needs_review   — ambiguous (mid-band model confidence, OCR-derived source,
                   conflicting methods, or partially matching values)

Design notes:
- Retrieval similarity and LLM self-evaluation are NEVER treated as proof;
  they only gate whether verification proceeds at all.
- OCR-sourced pages are flagged so users can inspect the original page.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from app.config import settings

SUPPORTED = "supported"
CONTRADICTED = "contradicted"
INSUFFICIENT = "insufficient"
NEEDS_REVIEW = "needs_review"


class VerificationUnavailable(Exception):
    pass


# ---------------------------------------------------------------------------
# Deterministic value extraction / checking
# ---------------------------------------------------------------------------

_CURRENCY_RE = re.compile(
    r"(?:[$€£]\s?|USD\s|EUR\s|GBP\s)\s?\d[\d,]*(?:\.\d{1,2})?", re.IGNORECASE
)
_PERCENT_RE = re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%")
# Legal drafts often spell out the numeral alongside the digits ("within thirty
# (30) days"). _PERIOD_RE only matches digits, so a paraphrase that drops the
# spelled-out word ("within 30 days") would look "missing". Normalize both
# phrasings to the same "30 days" form so the value check compares like-for-like.
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}
# Optional parenthetical numeral between the word and "days", e.g. "thirty (30) days".
_PAREN_NUM = r"(?:\s*\(\s*\d{1,3}\s*\))?"
_PERIOD_RE = re.compile(
    r"\b\d{1,4}\s+" + _PAREN_NUM + r"\s*(?:calendar\s+|business\s+|working\s+)?days?\b",
    re.IGNORECASE,
)
_SPELLING_RE = re.compile(
    r"\b(" + "|".join(_WORD_NUMBERS) + r")[\s-]*(?:\(\s*(\d{1,3})\s*\)|(\d{1,3}))?"
    r"\s*((?:calendar|business|working)\s+)?days?\b",
    re.IGNORECASE,
)


def _normalize_periods(text: str) -> list[str]:
    """Extract day-counts, resolving spelled-out numerals to digits.

    "within thirty (30) days" -> ["30 days"]; "within 30 days" -> ["30 days"].
    """
    if not text:
        return []
    out: list[str] = []

    def _unit_of(matched: str) -> str:
        unit = re.search(r"(calendar|business|working)\s+days?", matched, re.IGNORECASE)
        return f"{unit.group(1).lower()} days" if unit else "days"

    for m in _SPELLING_RE.finditer(text):
        # Prefer an explicit numeral; fall back to the spelled-out word's value.
        explicit = m.group(2) or m.group(3)
        num = int(explicit) if explicit else _WORD_NUMBERS[m.group(1).lower()]
        out.append(f"{num} {_unit_of(m.group(0))}")
    for m in _PERIOD_RE.finditer(text):
        out.append(re.sub(r"\s+", " ", m.group(0).lower()))
    # De-dup while preserving order.
    return list(dict.fromkeys(out))
_DATE_PATTERNS = [
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "%Y-%m-%d"),
    (re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"), "%m/%d/%Y"),
]
_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december|"
    "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
_LONG_DATE_RE = re.compile(
    rf"\b({_MONTHS})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.IGNORECASE
)
_DM_DATE_RE = re.compile(
    rf"\b(\d{{1,2}})\s+({_MONTHS})\.?,?\s+(\d{{4}})\b", re.IGNORECASE
)


def extract_dates(text: str) -> list[tuple[str, datetime | None]]:
    """Return (raw_expression, parsed_date_or_None) for dates in text."""
    out: list[tuple[str, datetime | None]] = []
    if not text:
        return out
    for pattern, fmt in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            try:
                out.append((m.group(0), datetime.strptime(m.group(0), fmt)))
            except ValueError:
                out.append((m.group(0), None))
    for m in _LONG_DATE_RE.finditer(text):
        raw = m.group(0)
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y")
        except ValueError:
            try:
                dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y")
            except ValueError:
                dt = None
        out.append((raw, dt))
    for m in _DM_DATE_RE.finditer(text):
        raw = m.group(0)
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y")
        except ValueError:
            try:
                dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %Y")
            except ValueError:
                dt = None
        out.append((raw, dt))
    return out


def _normalize_amount(raw: str) -> str:
    num = re.sub(r"[^\d.]", "", raw)
    try:
        return f"{float(num):.2f}"
    except ValueError:
        return raw.strip().lower()


def extract_structured_values(text: str) -> dict[str, list[str]]:
    """Extract checkable structured values from a claim."""
    if not text:
        return {"dates": [], "amounts": [], "percentages": [], "periods": []}
    dates = []
    for raw, parsed in extract_dates(text):
        dates.append(parsed.strftime("%Y-%m-%d") if parsed else raw.lower())
    return {
        "dates": dates,
        "amounts": [_normalize_amount(m.group(0)) for m in _CURRENCY_RE.finditer(text)],
        "percentages": [re.sub(r"\s", "", m.group(0)).lower() for m in _PERCENT_RE.finditer(text)],
        "periods": _normalize_periods(text),
    }


def deterministic_value_check(claim: str, evidence: str) -> dict:
    """Check structured values in `claim` against `evidence`.

    Returns {checked: int, matched: [...], missing: [...], conflicts: [...]}.
    A `conflict` is the same kind of value (date/amount) appearing in both
    texts with *different* values — a strong contradiction signal. `missing`
    values are weaker (paraphrase may omit them) and only degrade support.
    """
    claim_values = extract_structured_values(claim)
    evidence_norm = (evidence or "").lower()
    evidence_values = extract_structured_values(evidence or "")

    matched, missing, conflicts = [], [], []

    for kind in ("dates", "amounts", "percentages", "periods"):
        for value in claim_values[kind]:
            value_norm = value.lower()
            # presence check (substring, tolerant of formatting)
            if value_norm in evidence_norm or _value_present(value_norm, evidence_values[kind]):
                matched.append({"kind": kind, "value": value})
            elif evidence_values[kind]:
                # Same kind present in evidence but with different values → conflict
                conflicts.append({"kind": kind, "claim_value": value, "evidence_values": evidence_values[kind]})
            else:
                missing.append({"kind": kind, "value": value})

    checked = sum(len(v) for v in claim_values.values())
    return {"checked": checked, "matched": matched, "missing": missing, "conflicts": conflicts}


def _value_present(value: str, candidates: list[str]) -> bool:
    v = value.replace(",", "")
    for c in candidates:
        cn = c.replace(",", "")
        if v == cn or v in cn or cn in v:
            return True
    return False


# ---------------------------------------------------------------------------
# Semantic verifiers (NLI model or LLM judge)
# ---------------------------------------------------------------------------

_nli_pipeline = None
_nli_failed = False


def _get_nli_pipeline():
    """Lazy-load the NLI model. Returns None when unavailable (offline, etc.)."""
    global _nli_pipeline, _nli_failed
    if _nli_failed:
        return None
    if _nli_pipeline is not None:
        return _nli_pipeline
    try:
        from transformers import pipeline
        _nli_pipeline = pipeline(
            "text-classification",
            model=settings.VERIFIER_NLI_MODEL,
            top_k=None,
        )
    except Exception:  # noqa: BLE001 - any failure -> fall back gracefully
        _nli_failed = True
        return None
    return _nli_pipeline


def _resolve_provider() -> str:
    """Returns 'nli', 'llm', or 'off'."""
    provider = settings.VERIFIER_PROVIDER
    if provider == "off":
        return "off"
    if provider == "nli":
        return "nli" if _get_nli_pipeline() is not None else "off"
    if provider == "llm":
        return "llm"
    # auto
    return "nli" if _get_nli_pipeline() is not None else "llm"


def _truncate(text: str, max_chars: int = 1500) -> str:
    return text if len(text) <= max_chars else text[:max_chars] + "…"


def _nli_verdict(premise: str, hypothesis: str) -> tuple[str, float, str] | None:
    nli = _get_nli_pipeline()
    if nli is None:
        return None
    try:
        outputs = nli(_truncate(premise), _truncate(hypothesis))
    except Exception:  # noqa: BLE001
        return None
    if not outputs:
        return None
    scores = {o["label"].lower(): float(o["score"]) for o in outputs[0]}
    entail = scores.get("entailment", 0.0)
    contra = scores.get("contradiction", 0.0)
    neutral = scores.get("neutral", 0.0)
    if entail >= contra and entail >= neutral:
        verdict = SUPPORTED
        confidence = entail
    elif contra >= entail and contra >= neutral:
        verdict = CONTRADICTED
        confidence = contra
    else:
        verdict = INSUFFICIENT
        confidence = neutral
    return verdict, confidence, f"NLI ({settings.VERIFIER_NLI_MODEL}): {verdict} (p={confidence:.2f})"


_LLM_JUDGE_SYSTEM = (
    "You are a textual-entailment checker for LexClarity's verification engine. "
    "Given a CLAIM and EVIDENCE quoted from a legal document, decide ONLY whether "
    "the evidence textually supports, contradicts, or fails to establish the claim. "
    "This is a textual check, not a legal judgment. Never use outside knowledge. "
    "Respond with ONLY a JSON object: "
    '{"verdict": "supported" | "contradicted" | "insufficient" | "needs_review", '
    '"explanation": "one sentence citing the exact evidence words"}.'
    ' Use "needs_review" only when the evidence is genuinely ambiguous (e.g. pronouns '
    "or ellipsis make the referent unclear)."
)


def _llm_verdict(premise: str, hypothesis: str) -> tuple[str, float, str] | None:
    from app.services.llm import complete_json, LLMError

    prompt = (
        f"EVIDENCE (quoted from the document):\n{_truncate(premise)}\n\n"
        f"CLAIM to check:\n{_truncate(hypothesis)}\n\n"
        "Does the evidence support, contradict, or fail to establish the claim?"
    )
    try:
        result = complete_json(_LLM_JUDGE_SYSTEM, prompt, max_tokens=300)
    except LLMError:
        return None
    if not isinstance(result, dict):
        return None
    verdict = str(result.get("verdict", "")).lower()
    if verdict not in (SUPPORTED, CONTRADICTED, INSUFFICIENT, NEEDS_REVIEW):
        return None
    explanation = str(result.get("explanation", ""))[:500]
    # LLM self-evaluation is recorded as a judge opinion, never as proof.
    return verdict, 0.0, f"LLM textual-entailment judge: {verdict}. {explanation}".strip()


def semantic_verdict(premise: str, hypothesis: str) -> tuple[str, float, str] | None:
    provider = _resolve_provider()
    if provider == "off":
        return None
    if provider == "nli":
        result = _nli_verdict(premise, hypothesis)
        if result is not None:
            return result
        # nli failed at call time; try llm as a last resort in auto mode
        if settings.VERIFIER_PROVIDER == "auto":
            return _llm_verdict(premise, hypothesis)
        return None
    return _llm_verdict(premise, hypothesis)


# ---------------------------------------------------------------------------
# Claim verification
# ---------------------------------------------------------------------------

@dataclass
class Passage:
    text: str
    similarity: float = 1.0
    chunk_id: str | None = None
    page_number: int | None = None
    section_heading: str | None = None
    ocr_used: bool = False


@dataclass
class ClaimResult:
    claim: str
    status: str
    method: str
    explanation: str
    score: float | None = None
    evidence_chunk_id: str | None = None
    evidence_page: int | None = None
    evidence_excerpt: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "claim": self.claim,
            "status": self.status,
            "method": self.method,
            "explanation": self.explanation,
            "score": self.score,
            "evidence_chunk_id": self.evidence_chunk_id,
            "evidence_page": self.evidence_page,
            "evidence_excerpt": self.evidence_excerpt,
            "notes": self.notes,
        }


def split_claims(text: str) -> list[str]:
    """Split a generated answer into individual factual claims (sentences)."""
    from app.utils.text_cleaning import split_into_sentences

    if not text:
        return []
    sentences = split_into_sentences(text)
    out = []
    for s in sentences:
        s = s.strip()
        # Skip pure hedging / refusal sentences — not factual claims.
        if len(s.split()) < 4:
            continue
        out.append(s)
    return out


def verify_claim(claim: str, passages: list[Passage]) -> ClaimResult:
    """Verify one claim against its supporting source passages."""
    if not passages:
        return ClaimResult(
            claim=claim,
            status=INSUFFICIENT,
            method="unavailable",
            explanation="No source passages were associated with this claim.",
        )

    best = max(passages, key=lambda p: p.similarity)

    # Gate: retrieval similarity is a filter, not proof.
    if best.similarity < settings.VERIFICATION_MIN_SIMILARITY:
        return ClaimResult(
            claim=claim,
            status=INSUFFICIENT,
            method="deterministic",
            explanation=(
                f"Best matching passage is only weakly related to the claim "
                f"(similarity {best.similarity:.2f} < {settings.VERIFICATION_MIN_SIMILARITY})."
            ),
            score=round(best.similarity, 3),
            evidence_chunk_id=best.chunk_id,
            evidence_page=best.page_number,
            evidence_excerpt=_excerpt(best.text),
        )

    evidence_text = best.text
    checks = deterministic_value_check(claim, evidence_text)
    notes: list[str] = []
    if best.ocr_used:
        notes.append(
            "This passage came from OCR text; OCR errors are possible — inspect the original page."
        )

    # Hard contradiction from conflicting structured values.
    if checks["conflicts"]:
        kinds = {c["kind"] for c in checks["conflicts"]}
        if kinds & {"dates", "amounts", "percentages", "periods"}:
            detail = "; ".join(
                f"claim states {c['claim_value']} but evidence has {', '.join(c['evidence_values'][:3])}"
                for c in checks["conflicts"] if c["kind"] in {"dates", "amounts", "percentages", "periods"}
            )
            return ClaimResult(
                claim=claim,
                status=CONTRADICTED,
                method="deterministic",
                explanation=f"Structured values in the claim conflict with the source passage ({detail}).",
                score=round(best.similarity, 3),
                evidence_chunk_id=best.chunk_id,
                evidence_page=best.page_number,
                evidence_excerpt=_excerpt(evidence_text),
                notes=notes,
            )

    # A structured value (date/amount/percentage/day-count) the claim asserts is
    # NOT in the evidence. This is a deterministic signal that the semantic
    # verdict cannot override — a model "supported" opinion is never treated as
    # proof over a value check. Flag for human review instead of trusting it.
    missing_structured = list(checks["missing"])
    if missing_structured:
        missing_list = ", ".join(m["value"] for m in missing_structured[:4])
        verdict = semantic_verdict(evidence_text, claim)
        v_label = verdict[0] if verdict else "unavailable"
        return ClaimResult(
            claim=claim,
            status=NEEDS_REVIEW,
            method="deterministic",
            explanation=(
                f"The claim states structured value(s) that do not appear in the source passage "
                f"({missing_list}); the evidence does not establish them. "
                f"Semantic verdict was '{v_label}' but is not treated as proof."
            ),
            score=round(best.similarity, 3),
            evidence_chunk_id=best.chunk_id,
            evidence_page=best.page_number,
            evidence_excerpt=_excerpt(evidence_text),
            notes=notes + [
                f"Value(s) {missing_list} could not be located in the supporting passage — verify against the original document."
            ],
        )

    # Semantic entailment via configured verifier.
    verdict = semantic_verdict(evidence_text, claim)

    if verdict is None:
        # No semantic verifier available: fall back to value checks only.
        # Structured values were all matched (or the claim has none).
        if checks["checked"] > 0 and not checks["missing"] and not checks["conflicts"]:
            return ClaimResult(
                claim=claim,
                status=SUPPORTED,
                method="deterministic",
                explanation="All structured values in the claim (dates/amounts/percentages/periods) were found in the source passage. No semantic verifier was available.",
                score=round(best.similarity, 3),
                evidence_chunk_id=best.chunk_id,
                evidence_page=best.page_number,
                evidence_excerpt=_excerpt(evidence_text),
                notes=notes + ["Semantic verification unavailable; status based on deterministic value checks only."],
            )
        # No checkable values and no verifier: nothing establishes the claim.
        return ClaimResult(
            claim=claim,
            status=INSUFFICIENT,
            method="deterministic",
            explanation="No semantic verifier was available and the claim contains no structured values that could be checked against the source passage.",
            score=round(best.similarity, 3),
            evidence_chunk_id=best.chunk_id,
            evidence_page=best.page_number,
            evidence_excerpt=_excerpt(evidence_text),
            notes=notes + ["Semantic verification unavailable."],
        )

    v_label, v_confidence, v_explanation = verdict
    method = "nli" if v_label and settings.VERIFIER_PROVIDER != "llm" and "NLI" in v_explanation else "llm"

    status = v_label
    # Mid-band NLI confidence → ask a human to review rather than trusting it.
    if method == "nli" and 0.40 <= v_confidence < 0.65 and status in (SUPPORTED, INSUFFICIENT):
        status = NEEDS_REVIEW
        notes.append(f"NLI confidence was mid-band ({v_confidence:.2f}); flagged for human review.")
    # (Missing structured values are handled deterministically above and can
    # never be overridden by a "supported" verdict, so no downgrade is needed here.)
    if status == SUPPORTED and best.similarity < settings.VERIFICATION_SUPPORT_THRESHOLD:
        status = NEEDS_REVIEW
        notes.append(
            f"Supporting passage similarity is low ({best.similarity:.2f}); "
            "the match may be tangential."
        )
    if best.ocr_used and status == SUPPORTED:
        status = NEEDS_REVIEW

    return ClaimResult(
        claim=claim,
        status=status,
        method=method,
        explanation=v_explanation,
        score=round(v_confidence, 3) if method == "nli" else round(best.similarity, 3),
        evidence_chunk_id=best.chunk_id,
        evidence_page=best.page_number,
        evidence_excerpt=_excerpt(evidence_text),
        notes=notes,
    )


def _excerpt(text: str, max_chars: int = 260) -> str:
    text = (text or "").strip()
    return text if len(text) <= max_chars else text[:max_chars] + "…"


def verify_answer(answer: str, passages: list[Passage]) -> dict:
    """Verify every claim in a generated answer.

    Returns {"overall": ..., "claims": [ClaimResult.to_dict(), ...]} where
    overall is the worst status across claims (contradicted > needs_review >
    insufficient > supported).
    """
    claims = split_claims(answer)
    if not claims:
        return {"overall": INSUFFICIENT, "claims": []}
    results = [verify_claim(c, passages) for c in claims]
    order = {CONTRADICTED: 0, NEEDS_REVIEW: 1, INSUFFICIENT: 2, SUPPORTED: 3}
    overall = min((r.status for r in results), key=lambda s: order.get(s, 1))
    return {"overall": overall, "claims": [r.to_dict() for r in results]}


def summarize_claim_statuses(claims: list[dict]) -> str:
    """Human-readable one-liner for UI display."""
    counts: dict[str, int] = {}
    for c in claims:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    parts = [f"{n} {s.replace('_', ' ')}" for s, n in counts.items()]
    return ", ".join(parts)
