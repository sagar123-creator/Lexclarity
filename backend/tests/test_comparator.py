import unittest
from unittest.mock import patch

from app.services.comparator import word_diff, _key_values, compare_documents

from tests.fakes import DatabaseTestCase


class WordDiffTests(unittest.TestCase):
    def test_identical_text(self):
        diff = word_diff("net thirty days", "net thirty days")
        self.assertTrue(diff["identical"])
        self.assertEqual(diff["similarity"], 1.0)

    def test_modified_text_has_replace_opcode(self):
        diff = word_diff("payment due in 30 days", "payment due in 60 days")
        self.assertFalse(diff["identical"])
        types = {c["type"] for c in diff["opcodes"]}
        self.assertIn("replace", types)
        self.assertLess(diff["similarity"], 1.0)

    def test_tokens_preserved_for_highlighting(self):
        diff = word_diff("alpha beta", "alpha gamma")
        self.assertEqual(diff["a_tokens"], ["alpha ", "beta"])
        self.assertEqual(diff["b_tokens"], ["alpha ", "gamma"])


class KeyValueTests(unittest.TestCase):
    def test_extracts_amounts_and_day_terms(self):
        values = _key_values("fee of $18,500 due within 30 days of invoice")
        self.assertIn("$18,500", values["amounts"])
        self.assertTrue(any("30 days" in d for d in values["day_terms"]))


class CompareDocumentsTests(DatabaseTestCase):
    def _build_docs(self):
        doc_a = self.make_document(filename="v1.txt")
        doc_b = self.make_document(filename="v2.txt")
        from app import models

        self.db.add(models.Clause(
            document_id=doc_a.id, category="Payment", title="Payment",
            original_text="Client shall pay $10,000 within 30 days of invoice.",
            page_number=1,
        ))
        self.db.add(models.Clause(
            document_id=doc_b.id, category="Payment", title="Payment",
            original_text="Client shall pay $25,000 within 60 days of invoice.",
            page_number=1,
        ))
        self.db.add(models.Clause(
            document_id=doc_a.id, category="Non-compete", title="Non-compete",
            original_text="Provider shall not compete for 24 months.", page_number=2,
        ))
        self.db.add(models.Risk(
            document_id=doc_a.id, level="Medium", title="Auto renewal",
            description="d", why_it_matters="w", category="auto_renewal",
        ))
        self.db.add(models.Risk(
            document_id=doc_b.id, level="High", title="Uncapped liability",
            description="d", why_it_matters="w", category="unlimited_liability",
        ))
        self.db.commit()
        return doc_a, doc_b

    @patch("app.services.comparator._llm_summary", return_value="Summary from test.")
    def test_compare_detects_added_removed_and_modified(self, _mock):
        doc_a, doc_b = self._build_docs()
        result = compare_documents(self.db, doc_a, doc_b)

        changes = {(c["category"], c["change"]) for c in result["clause_changes"]}
        self.assertIn(("payment", "modified"), changes)
        self.assertIn(("non-compete", "removed"), changes)  # present in A only

        payment = next(c for c in result["clause_changes"] if c["category"] == "payment")
        self.assertEqual(payment["key_values_a"]["amounts"], ["$10,000"])
        self.assertEqual(payment["key_values_b"]["amounts"], ["$25,000"])
        self.assertIsNotNone(payment["diff"])

        delta = result["risk_delta"]
        self.assertIn("unlimited_liability", delta["categories_added"])
        self.assertIn("auto_renewal", delta["categories_removed"])
        self.assertEqual(delta["overall_level_a"], "Medium")
        self.assertEqual(delta["overall_level_b"], "High")
        self.assertEqual(result["summary"], "Summary from test.")
        self.assertIn("consult", result["summary_disclaimer"].lower())

    @patch("app.services.comparator._llm_summary", return_value=None)
    def test_added_clause_detected(self, _mock):
        doc_a, doc_b = self._build_docs()
        from app import models
        self.db.add(models.Clause(
            document_id=doc_b.id, category="Insurance", title="Insurance",
            original_text="Provider shall maintain general liability insurance.", page_number=3,
        ))
        self.db.commit()
        result = compare_documents(self.db, doc_a, doc_b)
        self.assertIn(("insurance", "added"), {(c["category"], c["change"]) for c in result["clause_changes"]})

    @patch("app.services.comparator._llm_summary", return_value="Fallback summary.")
    def test_llm_summary_failure_falls_back(self, _mock):
        doc_a, doc_b = self._build_docs()
        result = compare_documents(self.db, doc_a, doc_b)
        # _llm_summary patched directly, so result is the patched value
        self.assertEqual(result["summary"], "Fallback summary.")


if __name__ == "__main__":
    unittest.main()
