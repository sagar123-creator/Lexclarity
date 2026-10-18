import unittest
from datetime import datetime

from app.services.dates import normalize_date_expression, find_anchor_date


class NormalizeDateTests(unittest.TestCase):
    def test_long_form_date(self):
        result = normalize_date_expression("January 15, 2025")
        self.assertEqual(result["normalized_date"], "2025-01-15")
        self.assertEqual(result["date_kind"], "explicit")
        self.assertEqual(result["extraction_status"], "normalized")

    def test_day_first_date(self):
        result = normalize_date_expression("1 March 2026")
        self.assertEqual(result["normalized_date"], "2026-03-01")
        self.assertEqual(result["date_kind"], "explicit")

    def test_iso_date(self):
        result = normalize_date_expression("2026-03-01")
        self.assertEqual(result["normalized_date"], "2026-03-01")

    def test_relative_period_with_anchor_is_inferred(self):
        anchor = datetime(2025, 1, 15)
        result = normalize_date_expression("within 60 days of the Effective Date", anchor_date=anchor)
        self.assertEqual(result["normalized_date"], "2025-03-16")
        self.assertEqual(result["date_kind"], "inferred")
        self.assertEqual(result["extraction_status"], "normalized")

    def test_relative_period_without_anchor_is_raw(self):
        result = normalize_date_expression("within 30 days of termination")
        self.assertIsNone(result["normalized_date"])
        self.assertEqual(result["extraction_status"], "raw_only")

    def test_business_days_not_inferred(self):
        anchor = datetime(2025, 1, 15)
        result = normalize_date_expression("within 10 business days", anchor_date=anchor)
        self.assertIsNone(result["normalized_date"])
        self.assertEqual(result["extraction_status"], "raw_only")

    def test_month_year_without_day_is_uncertain(self):
        result = normalize_date_expression("March 2026")
        self.assertIsNone(result["normalized_date"])
        self.assertEqual(result["extraction_status"], "uncertain")

    def test_two_different_dates_is_uncertain(self):
        result = normalize_date_expression("between 2025-01-15 and 2026-03-01")
        self.assertIsNone(result["normalized_date"])
        self.assertEqual(result["extraction_status"], "uncertain")

    def test_empty_value(self):
        result = normalize_date_expression(None)
        self.assertEqual(result["extraction_status"], "raw_only")


class AnchorDetectionTests(unittest.TestCase):
    def test_finds_effective_date(self):
        items = [
            {"label": "Renewal", "date_value": "March 1, 2026"},
            {"label": "Effective Date", "date_value": "January 15, 2025"},
        ]
        anchor = find_anchor_date(items)
        self.assertIsNotNone(anchor)
        self.assertEqual(anchor.date().isoformat(), "2025-01-15")

    def test_no_anchor_returns_none(self):
        self.assertIsNone(find_anchor_date([{"label": "Payment", "date_value": "30 days"}]))


if __name__ == "__main__":
    unittest.main()
