import unittest
from unittest.mock import patch

from app import models
from app.services import generator

from tests.fakes import DatabaseTestCase, fake_llm


class GatherFindingsTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.doc = self.make_document(user_id=self.user.id)
        self.risk = models.Risk(
            document_id=self.doc.id, level="High", title="Unlimited liability",
            description="The clause is uncapped.", why_it_matters="May expose the party.",
            evidence_quote="NEITHER PARTY'S LIABILITY SHALL EXCEED...", page_number=6,
        )
        self.clause = models.Clause(
            document_id=self.doc.id, category="Payment", title="Payment",
            original_text="Client shall pay $18,500 monthly.",
            plain_explanation="Client pays monthly.", page_number=3,
        )
        self.db.add_all([self.risk, self.clause])
        self.db.commit()

    def test_selected_source_ids_filter_findings(self):
        findings = generator.gather_findings(self.db, self.doc.id, [self.risk.id])
        self.assertEqual(len(findings), 1)
        self.assertIn("Unlimited liability", findings[0].label)

    def test_no_selection_returns_all(self):
        findings = generator.gather_findings(self.db, self.doc.id, None)
        self.assertEqual(len(findings), 2)


class GenerateDraftTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.doc = self.make_document(user_id=self.user.id)
        self.risk = models.Risk(
            document_id=self.doc.id, level="High", title="Unlimited liability",
            description="Liability is uncapped.", why_it_matters="May expose the party.",
            evidence_quote="NEITHER PARTY'S LIABILITY SHALL EXCEED THE FEES PAID",
            page_number=6, suggested_action="Negotiate a cap.",
        )
        self.db.add(self.risk)
        self.db.commit()

    def test_unknown_template_kind_rejected(self):
        with self.assertRaises(ValueError):
            generator.generate_draft(self.db, self.doc, "love_letter")

    def test_draft_uses_placeholders_for_missing_facts(self):
        payload = {
            "title": "Negotiation email re: liability",
            "content": (
                "Dear [PLACEHOLDER: recipient name],\n\n"
                "We would like to discuss Section 6.1 of the agreement dated "
                "[PLACEHOLDER: agreement date].\n\nRegards,\n[PLACEHOLDER: sender name]"
            ),
        }
        with fake_llm([payload]):
            draft = generator.generate_draft(self.db, self.doc, "negotiation_email", source_ids=[self.risk.id])

        self.assertEqual(draft["kind"], "negotiation_email")
        self.assertEqual(len(draft["placeholders"]), 3)
        self.assertTrue(all(p.startswith("[PLACEHOLDER:") for p in draft["placeholders"]))
        # Source refs carry the real quote and page
        self.assertEqual(draft["source_refs"][0]["quote"], "NEITHER PARTY'S LIABILITY SHALL EXCEED THE FEES PAID")
        self.assertEqual(draft["source_refs"][0]["page_number"], 6)

    def test_prompt_contains_only_stored_finding_text(self):
        calls = []
        with fake_llm(lambda s, u: calls.append(u) or {"title": "t", "content": "c [PLACEHOLDER: x]"}):
            generator.generate_draft(self.db, self.doc, "lawyer_summary", source_ids=[self.risk.id])
        prompt = calls[0]
        self.assertIn("Liability is uncapped.", prompt)
        self.assertIn("NEITHER PARTY'S LIABILITY SHALL EXCEED THE FEES PAID", prompt)
        self.assertIn("[PLACEHOLDER:", prompt)  # rules instruct placeholders

    def test_malformed_llm_response_raises_value_error(self):
        with fake_llm([{"nope": True}]):
            with self.assertRaises(ValueError):
                generator.generate_draft(self.db, self.doc, "negotiation_email")

    def test_llm_error_becomes_value_error(self):
        from app.services.llm import LLMError
        with fake_llm([LLMError("provider down")]):
            with self.assertRaisesRegex(ValueError, "Draft generation failed"):
                generator.generate_draft(self.db, self.doc, "negotiation_email")

    def test_all_template_kinds_have_metadata(self):
        for kind in generator.TEMPLATE_KINDS:
            self.assertTrue(generator.TEMPLATE_KINDS[kind]["description"])


class DraftEditingTests(DatabaseTestCase):
    def test_editing_draft_marks_user_edited_and_recounts_placeholders(self):
        user = self.make_user()
        doc = self.make_document(user_id=user.id)
        draft = models.Draft(
            document_id=doc.id, kind="negotiation_email", title="T",
            content="Hello [PLACEHOLDER: name],", is_ai_generated=True, edited_by_user=False,
        )
        self.db.add(draft)
        self.db.commit()
        self.db.refresh(draft)
        self.assertEqual(len(draft.placeholders), 1)

        new_content = "Hello Maria,\nAll facts confirmed — no placeholders remain."
        draft.content = new_content
        draft.edited_by_user = True
        draft.placeholders = sorted(set(generator.PLACEHOLDER_RE.findall(new_content)))
        self.db.commit()
        self.db.refresh(draft)
        self.assertEqual(draft.placeholders, [])
        self.assertTrue(draft.edited_by_user)


if __name__ == "__main__":
    unittest.main()
