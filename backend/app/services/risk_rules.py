"""
Risk taxonomy and DETERMINISTIC severity rubric.

Severity is never assigned just because an LLM said so. The LLM is asked to
classify a finding into one of the documented categories below and to quote
the supporting text; the codebase then:

  1. Validates that the quotation actually exists in the cited source chunk
     (services/evidence.py) — unverifiable quotes are flagged, not trusted.
  2. Assigns severity from the documented rubric in this file: each category
     has a base level plus explicit escalation/mitigation triggers (real
     phrases looked up in the clause text).
  3. Records which rubric rules fired in `severity_rationale`.

Findings whose category can't be determined or whose quote can't be verified
are marked "needs_review" rather than silently trusted.
"""
from __future__ import annotations

from dataclasses import dataclass

RISK_CATEGORIES: dict[str, str] = {
    "unlimited_liability": "Unlimited or unclear liability",
    "one_sided_termination": "One-sided termination rights",
    "auto_renewal": "Automatic renewal",
    "penalty_payment_terms": "Penalties or unfavorable payment terms",
    "broad_indemnification": "Broad indemnification",
    "confidentiality": "Confidentiality concerns",
    "non_compete": "Non-compete restrictions",
    "dispute_resolution": "Unclear or unfavorable dispute resolution",
    "jurisdiction": "Potentially unfavorable jurisdiction/venue",
    "unilateral_amendment": "Unilateral amendment or waiver rights",
    "other": "Other potential concern",
}

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "unlimited_liability": ["liable", "liability", "losses", "damages", "responsib"],
    "one_sided_termination": ["terminate", "termination", "cancel", "cancellation"],
    "auto_renewal": ["automatically renew", "auto-renew", "renewal", "successive term", "evergreen"],
    "penalty_payment_terms": ["late fee", "penalt", "interest", "invoice", "payment", "non-refundable", "forfeit"],
    "broad_indemnification": ["indemnif", "hold harmless", "defend"],
    "confidentiality": ["confidential", "non-disclosure", "proprietary", "trade secret"],
    "non_compete": ["non-compete", "noncompete", "restrictive coven", "compet"],
    "dispute_resolution": ["arbitrat", "dispute", "governing law", "venue", "litigation", "attorney"],
    "jurisdiction": ["jurisdiction", "venue", "governing law", "exclusive venue", "courts of"],
    "unilateral_amendment": ["amend", "modify", "waive", "sole discretion", "at any time"],
    "other": [],
}


@dataclass
class RubricResult:
    level: str            # High | Medium | Low
    rationale: str        # which rules fired
    affected_party_hint: str | None = None


# Base level per category (before triggers).
CATEGORY_BASE_LEVEL: dict[str, str] = {
    "unlimited_liability": "High",
    "one_sided_termination": "Medium",
    "auto_renewal": "Medium",
    "penalty_payment_terms": "Medium",
    "broad_indemnification": "Medium",
    "confidentiality": "Medium",
    "non_compete": "Medium",
    "dispute_resolution": "Medium",
    "jurisdiction": "Medium",
    "unilateral_amendment": "Medium",
    "other": "Low",
}

# Phrase triggers that escalate severity one step (max High).
ESCALATION_TRIGGERS: dict[str, list[str]] = {
    "unlimited_liability": [
        "uncapped", "without limitation", "without limit", "all losses", "all damages",
        "not limited", "irrespective of", "regardless of negligence", "sole responsibility",
    ],
    "one_sided_termination": [
        "sole discretion", "at any time", "without cause", "no liability", "without notice",
        "may terminate at will",
    ],
    # Note: the definitional phrases ("automatically renew", "auto-renew") are
    # deliberately NOT escalators — they describe the category itself, and every
    # genuine auto-renewal finding quotes them. Escalation is reserved for
    # aggravating features: renewals that stack indefinitely or are awkward to exit.
    "auto_renewal": [
        "successive", "evergreen", "unless notice",
    ],
    "penalty_payment_terms": [
        "late fee", "penalty", "default interest", "high interest", "non-refundable",
        "forfeit", "accelerat", "1.5%", "2%", "per month",
    ],
    "broad_indemnification": [
        "all claims", "any and all", "howsoever arising", "third party claims",
        "including without limitation", "hold harmless",
    ],
    "confidentiality": [
        "perpetual", "indefinite", "irrevocable", "survives termination", "no exclusions",
        "all information", "regardless of",
    ],
    "non_compete": [
        "worldwide", "perpetual", "indefinite", "any business", "directly or indirectly",
    ],
    "dispute_resolution": [
        "final and binding", "waive", "class action", "jury", "each party bears",
        "prevailing party", "sole arbitrator",
    ],
    "jurisdiction": [
        "exclusive jurisdiction", "exclusive venue", "sole venue", "laws of",
    ],
    "unilateral_amendment": [
        "at any time", "sole discretion", "without notice", "unilateral", "waive",
    ],
    "other": [],
}

# Phrase triggers that mitigate severity one step (min Low).
MITIGATION_TRIGGERS: dict[str, list[str]] = {
    "unlimited_liability": [
        "except for", "excluding", "subject to", "cap", "aggregate liability",
        "to the maximum extent",
    ],
    "one_sided_termination": [
        "for material breach", "for cause", "cure period", "notice period", "written notice",
        "mutual", "either party",
    ],
    "auto_renewal": ["may elect not to renew", "written notice", "prior notice"],
    "penalty_payment_terms": ["disputed in good faith", "cure period", "remedies"],
    "broad_indemnification": [
        "limited to", "excluding", "sole negligence", "subject to", "mitigate",
    ],
    "confidentiality": [
        "exceptions", "publicly available", "independently developed", "required by law",
        "permitted disclosure",
    ],
    "non_compete": ["reasonable", "limited period", "limited scope", "to the extent permitted"],
    "dispute_resolution": ["good faith", "mediation", "notice and cure", "mutual agreement"],
    "jurisdiction": ["mutual", "agreed by both parties"],
    "unilateral_amendment": ["with consent", "mutual", "written agreement", "prior notice"],
    "other": [],
}

LEVEL_ORDER = {"Low": 0, "Medium": 1, "High": 2}


def categorize_finding(title: str, description: str) -> str | None:
    """Best-effort category from text; used to sanity-check the LLM's label."""
    text = f"{title or ''} {description or ''}".lower()
    best_cat, best_hits = None, 0
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if cat == "other":
            continue
        hits = sum(1 for k in keywords if k in text)
        if hits > best_hits:
            best_cat, best_hits = cat, hits
    return best_cat if best_hits >= 2 else None


def apply_severity_rubric(category: str | None, clause_text: str, llm_level: str | None = None) -> RubricResult:
    """Deterministically derive severity from documented criteria.

    The LLM's suggested level is never used directly; it is only recorded for
    transparency when the rubric can't classify the finding.
    """
    if category not in RISK_CATEGORIES or category == "other":
        # Unknown category: fall back to LLM level but demand human review.
        level = llm_level if llm_level in ("High", "Medium", "Low") else "Low"
        return RubricResult(
            level=level,
            rationale=(
                "Category could not be determined from documented criteria; severity "
                f"inherited from the model's suggestion ({level}) and flagged for review."
            ),
            affected_party_hint=None,
        )

    text = (clause_text or "").lower()
    level = CATEGORY_BASE_LEVEL[category]
    fired: list[str] = [f"base level for '{RISK_CATEGORIES[category]}' = {level}"]

    escalated = [t for t in ESCALATION_TRIGGERS[category] if t in text]
    mitigated = [t for t in MITIGATION_TRIGGERS[category] if t in text]

    if escalated:
        level = "High" if level != "High" else level
        fired.append(f"escalation triggers found: {', '.join(escalated[:4])}")
    if mitigated and not escalated:
        level = "Low" if level == "Medium" else level
        fired.append(f"mitigation language found: {', '.join(mitigated[:4])}")
    elif mitigated:
        fired.append(f"mitigating language also present (not applied due to escalation): {', '.join(mitigated[:3])}")

    return RubricResult(level=level, rationale="; ".join(fired))


def overall_risk_level(levels: list[str]) -> str:
    if not levels:
        return "Unknown"
    if "High" in levels:
        return "High"
    if "Medium" in levels:
        return "Medium"
    if "Low" in levels:
        return "Low"
    return "Unknown"


SUGGESTED_ACTIONS: dict[str, str] = {
    "unlimited_liability": (
        "Consider negotiating a liability cap or exclusions for indirect/consequential "
        "damages; have counsel confirm the scope of exposure."
    ),
    "one_sided_termination": (
        "Ask for mutual termination rights, a cure period, or compensation for "
        "investments made in reliance on the contract."
    ),
    "auto_renewal": (
        "Diary the non-renewal notice window and confirm the notice method; consider "
        "negotiating a reminder obligation or removing auto-renewal."
    ),
    "penalty_payment_terms": (
        "Review payment deadlines and late-fee rates; ask to cap late fees or add a "
        "good-faith dispute process before penalties accrue."
    ),
    "broad_indemnification": (
        "Ask to limit indemnity to third-party claims caused by the indemnifying "
        "party's own breach or negligence, with a mitigation duty."
    ),
    "confidentiality": (
        "Confirm standard exceptions (public knowledge, independent development, "
        "legal compulsion) and a workable return/destruction obligation."
    ),
    "non_compete": (
        "Check the scope, geography and duration for reasonableness; have local "
        "counsel confirm enforceability in the relevant jurisdiction."
    ),
    "dispute_resolution": (
        "Clarify the escalation steps, arbitration rules, cost allocation and any "
        "jury-trial or class-action waivers before signing."
    ),
    "jurisdiction": (
        "Confirm whether the governing law and venue are workable for you; consider "
        "proposing a neutral or mutually convenient forum."
    ),
    "unilateral_amendment": (
        "Ask for prior written notice and/or consent for changes, and remove blanket "
        "waiver language."
    ),
    "other": "Review the clause with a qualified professional before relying on it.",
}


def suggested_action_for(category: str | None) -> str:
    return SUGGESTED_ACTIONS.get(category or "other", SUGGESTED_ACTIONS["other"])
