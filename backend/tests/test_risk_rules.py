import unittest

from app.services import risk_rules as R


class CategorizeTests(unittest.TestCase):
    def test_categorizes_liability(self):
        cat = R.categorize_finding(
            "Unlimited Liability",
            "The clause makes the provider liable for all losses without limitation.",
        )
        self.assertEqual(cat, "unlimited_liability")

    def test_categorizes_auto_renewal(self):
        cat = R.categorize_finding(
            "Automatic Renewal",
            "The agreement automatically renews for successive terms unless notice is given.",
        )
        self.assertEqual(cat, "auto_renewal")

    def test_returns_none_for_weak_signal(self):
        self.assertIsNone(R.categorize_finding("Odd clause", "Something unrelated entirely."))


class SeverityRubricTests(unittest.TestCase):
    def test_base_level_applied(self):
        result = R.apply_severity_rubric("confidentiality", "Each party shall keep information confidential.")
        self.assertEqual(result.level, "Medium")
        self.assertIn("base level", result.rationale)

    def test_escalation_trigger_raises_to_high(self):
        clause = "The provider's liability shall be uncapped and without limitation for all losses."
        result = R.apply_severity_rubric("unlimited_liability", clause)
        self.assertEqual(result.level, "High")
        self.assertIn("escalation", result.rationale)

    def test_mitigation_language_lowers_to_low(self):
        clause = "Each party shall keep information confidential, subject to standard exceptions for publicly available information."
        result = R.apply_severity_rubric("confidentiality", clause)
        self.assertEqual(result.level, "Low")
        self.assertIn("mitigation", result.rationale)

    def test_escalation_wins_over_mitigation(self):
        clause = (
            "Liability is uncapped and without limitation, except for excluding indirect damages "
            "to the maximum extent permitted."
        )
        result = R.apply_severity_rubric("unlimited_liability", clause)
        self.assertEqual(result.level, "High")
        self.assertIn("not applied due to escalation", result.rationale)

    def test_llm_level_never_used_for_known_category(self):
        result = R.apply_severity_rubric("auto_renewal", "This agreement shall automatically renew.", llm_level="Low")
        self.assertEqual(result.level, "Medium")  # rubric base, not the LLM's "Low"
        self.assertNotIn("Low)", result.rationale.split("escalation")[0])

    def test_unknown_category_falls_back_and_flags_review(self):
        result = R.apply_severity_rubric("other", "some text", llm_level="High")
        self.assertEqual(result.level, "High")
        self.assertIn("flagged for review", result.rationale)

    def test_unknown_category_without_llm_level_defaults_low(self):
        result = R.apply_severity_rubric(None, "text", llm_level=None)
        self.assertEqual(result.level, "Low")


class SuggestedActionTests(unittest.TestCase):
    def test_every_category_has_a_suggested_action(self):
        for cat in R.RISK_CATEGORIES:
            self.assertTrue(R.suggested_action_for(cat))

    def test_unknown_category_gets_generic_action(self):
        self.assertIn("qualified professional", R.suggested_action_for(None))


class OverallLevelTests(unittest.TestCase):
    def test_high_dominates(self):
        self.assertEqual(R.overall_risk_level(["Low", "High", "Medium"]), "High")

    def test_empty_is_unknown(self):
        self.assertEqual(R.overall_risk_level([]), "Unknown")


if __name__ == "__main__":
    unittest.main()
