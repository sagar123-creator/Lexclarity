"""
Date normalization for the deadline tracker.

Distinguishes:
  - explicit calendar dates ("March 1, 2026", "2026-03-01") → normalized to ISO
  - relative durations ("within 30 days of the Effective Date") → kept as raw
    text with date_kind="inferred" only when an anchor date is available and
    the arithmetic is unambiguous; otherwise extraction_status="raw_only".

Nothing is ever invented: when a date cannot be reliably determined,
normalized_date stays None and the status says so.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.services.verification import extract_dates

_EFFECTIVE_ANCHOR_RE = re.compile(
    r"(effective date|start date|commencement date|commencement|execution date)",
    re.IGNORECASE,
)

_PERIOD_ANCHOR_RE = re.compile(
    r"(?:within|after|from|of|before)\s+(\d{1,4})\s+(calendar\s+|business\s+|working\s+)?days?",
    re.IGNORECASE,
)


def normalize_date_expression(raw: str | None, anchor_date: datetime | None = None) -> dict:
    """Try to normalize a raw date expression.

    Returns {normalized_date, date_kind, extraction_status} where:
      normalized_date: "YYYY-MM-DD" or None
      date_kind:       "explicit" | "inferred" | None
      extraction_status: "normalized" | "raw_only" | "uncertain"
    """
    if not raw or not raw.strip():
        return {"normalized_date": None, "date_kind": None, "extraction_status": "raw_only"}

    text = raw.strip()

    # 1. Direct calendar date in the expression.
    matches = extract_dates(text)
    if matches:
        # Prefer a fully parsed date.
        parsed = [m for m in matches if m[1] is not None]
        if parsed:
            # If multiple dates, don't guess — only normalize when unambiguous.
            distinct = {m[1].date().isoformat() for m in parsed}
            if len(distinct) == 1:
                return {
                    "normalized_date": parsed[0][1].date().isoformat(),
                    "date_kind": "explicit",
                    "extraction_status": "normalized",
                }
            return {
                "normalized_date": None,
                "date_kind": "explicit",
                "extraction_status": "uncertain",
            }
        return {
            "normalized_date": None,
            "date_kind": "explicit",
            "extraction_status": "uncertain",
        }

    # 2. Relative period tied to an anchor date we know.
    m = _PERIOD_ANCHOR_RE.search(text)
    if m and anchor_date is not None:
        days = int(m.group(1))
        # Business-day periods are not determinable without a calendar — skip.
        if m.group(2) and m.group(2).strip().lower().startswith("business"):
            return {
                "normalized_date": None,
                "date_kind": "inferred",
                "extraction_status": "raw_only",
            }
        sign = -1 if re.search(r"\bbefore\b", text, re.IGNORECASE) else 1
        computed = anchor_date + timedelta(days=sign * days)
        return {
            "normalized_date": computed.date().isoformat(),
            "date_kind": "inferred",
            "extraction_status": "normalized",
        }

    # 3. Month/year without a day (e.g. "March 2026") → uncertain.
    month_year = re.match(
        r"^(january|february|march|april|may|june|july|august|september|october|november|december)"
        r"\s+(\d{4})$",
        text,
        re.IGNORECASE,
    )
    if month_year:
        return {
            "normalized_date": None,
            "date_kind": "explicit",
            "extraction_status": "uncertain",
        }

    return {"normalized_date": None, "date_kind": None, "extraction_status": "raw_only"}


def find_anchor_date(items: list[dict]) -> datetime | None:
    """Locate an anchor (effective/start) date from extracted date items."""
    for item in items:
        label = (item.get("label") or "").lower()
        value = item.get("date_value") or item.get("normalized_date") or ""
        if _EFFECTIVE_ANCHOR_RE.search(label) or _EFFECTIVE_ANCHOR_RE.search(value):
            matches = extract_dates(value)
            parsed = [m[1] for m in matches if m[1] is not None]
            if parsed:
                return parsed[0]
    return None
