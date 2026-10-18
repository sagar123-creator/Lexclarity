import unittest
from unittest.mock import patch

from app.services import verification as V


EVIDENCE = (
    "This Agreement is entered into as of February 1, 2025. "
    "Client shall pay Service Provider a monthly fee of $18,500, due within thirty (30) "
    "days of receipt of invoice. Late payments shall accrue interest at 1.5% per month."
)


def passage(text=EVIDENCE, similarity=0.9, ocr=False, chunk_id="chunk-1", page=2):
    return V.Passage(
        text=text, similarity=similarity, chunk_id=chunk_id,
        page_number=page, section_heading="Payment", ocr_used=ocr,
    )


class DeterministicValueCheckTests(unittest.TestCase):
    def test_matched_date_and_amount(self):
        claim = "Payment of $18,500 is due within 30 days of invoice."
        result = V.deterministic_value_check(claim, EVIDENCE)
        kinds = {m["kind"] for m in result["matched"]}
        self.assertIn("amounts", kinds)
        self.assertIn("periods", kinds)
        self.assertEqual(result["conflicts"], [])

    def test_conflicting_amount_is_a_conflict(self):
        claim = "Payment of $25,000 is due within 30 days."
        result = V.deterministic_value_check(claim, EVIDENCE)
        amount_conflicts = [c for c in result["conflicts"] if c["kind"] == "amounts"]
        self.assertTrue(amount_conflicts)
        self.assertIn("25000.00", amount_conflicts[0]["claim_value"])

    def test_conflicting_date_is_a_conflict(self):
        evidence = "The agreement starts on January 15, 2025."
        claim = "The agreement starts on March 1, 2026."
        result = V.deterministic_value_check(claim, evidence)
        date_conflicts = [c for c in result["conflicts"] if c["kind"] == "dates"]
        self.assertTrue(date_conflicts)

    def test_missing_value_is_recorded(self):
        claim = "Payment of $99,999 is due."
        result = V.deterministic_value_check(claim, EVIDENCE)
        self.assertTrue(result["missing"] or result["conflicts"])


class VerifyClaimTests(unittest.TestCase):
    def test_low_similarity_is_insufficient(self):
        result = V.verify_claim("Something unrelated.", [passage(similarity=0.05)])
        self.assertEqual(result.status, V.INSUFFICIENT)
        self.assertEqual(result.method, "deterministic")

    def test_value_conflict_is_contradicted_deterministically(self):
        with patch.object(V, "semantic_verdict", return_value=(V.SUPPORTED, 0.9, "NLI: supported (p=0.90)")):
            result = V.verify_claim(
                "The monthly fee is $25,000.", [passage()]
            )
        self.assertEqual(result.status, V.CONTRADICTED)
        self.assertEqual(result.method, "deterministic")
        self.assertIn("conflict", result.explanation.lower())

    def test_entailment_is_supported(self):
        with patch.object(V, "semantic_verdict", return_value=(V.SUPPORTED, 0.93, "NLI: supported (p=0.93)")):
            result = V.verify_claim(
                "Client shall pay a monthly fee of $18,500, due within thirty (30) days of receipt of invoice.",
                [passage()],
            )
        self.assertEqual(result.status, V.SUPPORTED)
        self.assertEqual(result.evidence_chunk_id, "chunk-1")
        self.assertEqual(result.evidence_page, 2)

    def test_contradiction_is_contradicted(self):
        with patch.object(V, "semantic_verdict", return_value=(V.CONTRADICTED, 0.88, "NLI: contradicted (p=0.88)")):
            result = V.verify_claim("The agreement has no payment obligations.", [passage()])
        self.assertEqual(result.status, V.CONTRADICTED)

    def test_neutral_is_insufficient(self):
        with patch.object(V, "semantic_verdict", return_value=(V.INSUFFICIENT, 0.70, "NLI: insufficient (p=0.70)")):
            result = V.verify_claim("The office dog is walked daily.", [passage()])
        self.assertEqual(result.status, V.INSUFFICIENT)

    def test_mid_band_nli_confidence_requires_review(self):
        with patch.object(V, "semantic_verdict", return_value=(V.SUPPORTED, 0.52, "NLI: supported (p=0.52)")):
            result = V.verify_claim("Client shall pay a monthly fee of $18,500.", [passage()])
        self.assertEqual(result.status, V.NEEDS_REVIEW)

    def test_ocr_source_is_flagged_for_review(self):
        with patch.object(V, "semantic_verdict", return_value=(V.SUPPORTED, 0.95, "NLI: supported (p=0.95)")):
            result = V.verify_claim(
                "Client shall pay a monthly fee of $18,500, due within thirty (30) days of receipt of invoice.",
                [passage(ocr=True)],
            )
        self.assertEqual(result.status, V.NEEDS_REVIEW)
        self.assertTrue(any("OCR" in n for n in result.notes))

    def test_missing_values_with_entailment_degrade_to_review(self):
        # Passage without the late-payment rate: the claim's "1.5%" has no
        # support here, so an NLI "supported" verdict must not be trusted.
        passage_no_rate = passage(text=(
            "Client shall pay Service Provider a monthly fee of $18,500, due within "
            "thirty (30) days of receipt of invoice."
        ))
        with patch.object(V, "semantic_verdict", return_value=(V.SUPPORTED, 0.9, "NLI: supported (p=0.90)")):
            result = V.verify_claim(
                "Client shall pay $18,500 monthly, and interest accrues at 1.5% per month on the outstanding balance, and invoices are issued on the first business day of each month.",
                [passage_no_rate],
            )
        self.assertEqual(result.status, V.NEEDS_REVIEW)

    def test_no_verifier_matched_values_is_supported(self):
        with patch.object(V, "semantic_verdict", return_value=None):
            result = V.verify_claim("Payment of $18,500 is due within 30 days.", [passage()])
        self.assertEqual(result.status, V.SUPPORTED)
        self.assertEqual(result.method, "deterministic")
        self.assertTrue(any("unavailable" in n.lower() for n in result.notes))

    def test_no_verifier_no_values_is_insufficient(self):
        with patch.object(V, "semantic_verdict", return_value=None):
            result = V.verify_claim("Payment obligations exist under this contract.", [passage()])
        self.assertEqual(result.status, V.INSUFFICIENT)

    def test_no_passages_is_insufficient(self):
        result = V.verify_claim("Anything.", [])
        self.assertEqual(result.status, V.INSUFFICIENT)


class VerifyAnswerTests(unittest.TestCase):
    def test_overall_takes_worst_claim_status(self):
        answer = (
            "Client shall pay a monthly fee of $18,500, due within thirty (30) days of receipt of invoice. "
            "The agreement starts on January 15, 2025."
        )
        # First claim supported, second contradicts evidence date.
        with patch.object(V, "semantic_verdict", return_value=(V.SUPPORTED, 0.92, "NLI: supported (p=0.92)")):
            result = V.verify_answer(answer, [passage()])
        self.assertEqual(result["overall"], V.CONTRADICTED)
        self.assertEqual(len(result["claims"]), 2)

    def test_all_supported_overall(self):
        answer = "Client shall pay a monthly fee of $18,500, due within thirty (30) days of receipt of invoice."
        with patch.object(V, "semantic_verdict", return_value=(V.SUPPORTED, 0.92, "NLI: supported (p=0.92)")):
            result = V.verify_answer(answer, [passage()])
        self.assertEqual(result["overall"], V.SUPPORTED)

    def test_split_claims_skips_fragments(self):
        claims = V.split_claims("Yes. Client shall pay a monthly fee of $18,500 due within thirty days of invoice.")
        self.assertEqual(len(claims), 1)


class ProviderResolutionTests(unittest.TestCase):
    def test_off_provider_returns_none(self):
        with patch.object(V.settings, "VERIFIER_PROVIDER", "off"):
            self.assertIsNone(V.semantic_verdict("p", "h"))

    def test_summarize_claim_statuses(self):
        text = V.summarize_claim_statuses([{"status": "supported"}, {"status": "supported"}, {"status": "needs_review"}])
        self.assertIn("2 supported", text)
        self.assertIn("1 needs review", text)


if __name__ == "__main__":
    unittest.main()
