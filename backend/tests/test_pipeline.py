"""End-to-end pipeline regression with mocked LLM + fake retrieval.

Covers: upload-style processing, page persistence, enriched extraction,
verification statuses, checklist creation, action-item creation, date
normalization, and re-run idempotence.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from app import models
from app.services.pipeline import process_document

from tests.fakes import DatabaseTestCase, fake_retrieval, fake_llm

DOC_TEXT = """MASTER SERVICE AGREEMENT

This Agreement is entered into as of January 15, 2025 by between ACME CORP ("Client") and BETA SERVICES LLC ("Provider").

1. PAYMENT TERMS

Client shall pay Provider a monthly fee of $12,000 due within thirty (30) days of receipt of invoice. Late payments shall accrue interest at 1.5% per month.

2. TERMINATION

Either Party may terminate this Agreement for any reason upon ninety (90) days prior written notice to the other Party.

3. LIABILITY

Provider's liability arising out of this Agreement shall be uncapped and without limitation for all losses of any kind.

4. RENEWAL

This Agreement shall automatically renew for successive twelve (12) month periods unless either Party provides written notice of non-renewal.
"""


def build_llm_responder(store, document_id):
    """Route scripted LLM responses by prompt content, grounding quotes in
    whatever chunks the fake retrieval store actually holds."""

    def _first_chunk():
        chunks = store.store.get(document_id, [])
        return chunks[0] if chunks else None

    def responder(system, user):
        chunk = _first_chunk()
        quote = " ".join(chunk["text"].split()[:8]) if chunk else "placeholder quote"
        chunk_id = chunk["chunk_id"] if chunk else None
        page = chunk["page_number"] if chunk else 1

        if "executive_summary" in user:
            return {
                "document_type": "Service Agreement",
                "executive_summary": "A master service agreement between Client and Provider.",
                "plain_english_overview": "The document sets payment, termination, liability and renewal terms.",
            }
        if "Extract every party" in user:
            return [
                {"name": "ACME CORP", "role": "Client", "entity_type": "organization"},
                {"name": "BETA SERVICES LLC", "role": "Provider", "entity_type": "organization"},
            ]
        if "Extract concrete obligations" in user:
            return [{
                "party_name": "Client",
                "obligation_text": "Client shall pay Provider a monthly fee within thirty (30) days of invoice.",
                "deadline_text": "within thirty (30) days of receipt of invoice",
                "trigger_event": "receipt of invoice",
                "conditions": None,
                "quote": quote,
                "chunk_id": chunk_id,
                "page_number": page,
            }]
        if "Extract important dates" in user:
            return [{
                "label": "Effective Date",
                "date_value": "January 15, 2025",
                "description": "Agreement start date.",
                "quote": quote,
                "chunk_id": chunk_id,
                "page_number": page,
            }]
        if "Identify which of these clause categories" in user:
            return [{
                "category": "Termination",
                "title": "Termination for convenience",
                "original_text": quote,
                "plain_explanation": "Either party can end the deal with 90 days notice.",
                "parties": ["Client", "Provider"],
                "rights_obligations": "Either party may terminate on 90 days written notice.",
                "concerns": None,
                "chunk_id": chunk_id,
                "page_number": page,
            }]
        if "risk-analysis" in (system or ""):
            return [{
                "category": "unlimited_liability",
                "title": "Uncapped Liability",
                "affected_party": "Provider",
                "description": "Provider's liability is uncapped and without limitation.",
                "why_it_matters": "This clause may expose Provider to potentially unlimited losses.",
                "plain_explanation": "There is no monetary ceiling on Provider's exposure.",
                "quote": quote,
                "chunk_id": chunk_id,
                "page_number": page,
            }]
        if "Checklist item" in user:
            return {
                "state": "detected" if chunk else "not_detected",
                "explanation": "The excerpts address this checklist topic.",
                "quote": quote,
                "chunk_id": chunk_id,
            }
        return []

    return responder


class PipelineRegressionTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user("pipe-user")
        tmp = tempfile.mkdtemp(prefix="lexclarity-doc-")
        self.doc_path = os.path.join(tmp, "contract.txt")
        with open(self.doc_path, "w", encoding="utf-8") as f:
            f.write(DOC_TEXT)

        self.doc = models.Document(
            user_id=self.user.id, filename="contract.txt", file_type="txt",
            file_size_bytes=len(DOC_TEXT), storage_path=self.doc_path, status="uploaded",
        )
        self.db.add(self.doc)
        self.db.commit()
        self.db.refresh(self.doc)

    def _run_pipeline(self, store=None, responder=None):
        with fake_retrieval(store) as active_store:
            responder = responder or build_llm_responder(active_store, self.doc.id)
            with fake_llm(responder), patch(
                "app.services.verification.semantic_verdict", return_value=None
            ):
                process_document(self.db, self.doc)
        self.db.refresh(self.doc)
        return active_store

    def test_pipeline_produces_full_analysis(self):
        self._run_pipeline()
        self.assertEqual(self.doc.status, "ready", self.doc.error_message)
        self.assertEqual(self.doc.extraction_method, "text")
        self.assertFalse(self.doc.ocr_used)
        self.assertEqual(self.doc.document_type, "Service Agreement")

        # Pages persisted for the evidence viewer
        pages = self.db.query(models.DocumentPage).filter_by(document_id=self.doc.id).all()
        self.assertGreaterEqual(len(pages), 1)
        self.assertIn("MASTER SERVICE AGREEMENT", pages[0].text)

        # Chunks persisted
        self.assertGreater(self.db.query(models.DocumentChunk).filter_by(document_id=self.doc.id).count(), 0)

        # Enriched risks with rubric + verification
        risk = self.db.query(models.Risk).filter_by(document_id=self.doc.id).one()
        self.assertEqual(risk.category, "unlimited_liability")
        self.assertEqual(risk.level, "High")  # uncapped -> escalation trigger in rubric
        self.assertIn("escalation", risk.severity_rationale)
        self.assertTrue(risk.evidence_quote)
        self.assertTrue(risk.suggested_action)
        self.assertIn(risk.verification_status, {"supported", "contradicted", "insufficient", "needs_review"})
        self.assertEqual(self.doc.overall_risk_level, "High")

        # Clauses enriched
        clause = self.db.query(models.Clause).filter_by(document_id=self.doc.id).one()
        self.assertIsNotNone(clause.parties)
        self.assertTrue(clause.rights_obligations)
        self.assertIn(clause.verification_status, {"supported", "needs_review", "unverified", "insufficient", "contradicted"})

        # Obligations enriched
        obligation = self.db.query(models.Obligation).filter_by(document_id=self.doc.id).one()
        self.assertEqual(obligation.task_status, "pending")
        self.assertEqual(obligation.deadline_text, "within thirty (30) days of receipt of invoice")

        # Dates normalized as explicit
        date = self.db.query(models.ImportantDate).filter_by(document_id=self.doc.id).one()
        self.assertEqual(date.normalized_date, "2025-01-15")
        self.assertEqual(date.date_kind, "explicit")

        # Checklist created for the detected document type
        checklist = self.db.query(models.ChecklistItem).filter_by(document_id=self.doc.id).all()
        self.assertEqual(len(checklist), 9)  # Service Agreement checklist
        for item in checklist:
            self.assertIn(item.state, {"detected", "not_detected", "unclear", "not_applicable"})

        # Action items auto-created from findings
        actions = self.db.query(models.ActionItem).filter_by(document_id=self.doc.id).all()
        self.assertGreaterEqual(len(actions), 1)
        risk_action = next(a for a in actions if a.source_type == "risk")
        self.assertEqual(risk_action.decision, "undecided")

    def test_rerun_does_not_duplicate_rows(self):
        self._run_pipeline()
        counts = {
            "risks": self.db.query(models.Risk).filter_by(document_id=self.doc.id).count(),
            "clauses": self.db.query(models.Clause).filter_by(document_id=self.doc.id).count(),
            "pages": self.db.query(models.DocumentPage).filter_by(document_id=self.doc.id).count(),
            "chunks": self.db.query(models.DocumentChunk).filter_by(document_id=self.doc.id).count(),
            "actions": self.db.query(models.ActionItem).filter_by(document_id=self.doc.id).count(),
        }
        self._run_pipeline()
        self.assertEqual(
            counts,
            {
                "risks": self.db.query(models.Risk).filter_by(document_id=self.doc.id).count(),
                "clauses": self.db.query(models.Clause).filter_by(document_id=self.doc.id).count(),
                "pages": self.db.query(models.DocumentPage).filter_by(document_id=self.doc.id).count(),
                "chunks": self.db.query(models.DocumentChunk).filter_by(document_id=self.doc.id).count(),
                "actions": self.db.query(models.ActionItem).filter_by(document_id=self.doc.id).count(),
            },
        )

    def test_decided_action_survives_rerun(self):
        self._run_pipeline()
        action = self.db.query(models.ActionItem).first()
        action.decision = "accepted"
        self.db.commit()

        self._run_pipeline()
        self.db.expire_all()
        survived = self.db.query(models.ActionItem).filter_by(document_id=self.doc.id).all()
        self.assertTrue(any(a.decision == "accepted" for a in survived))

    def test_provider_outage_fails_document_gracefully(self):
        from app.services.llm import LLMError

        def outage(system, user):
            raise LLMError("Gemini API quota or rate limit reached.")

        self._run_pipeline(responder=outage)
        self.assertEqual(self.doc.status, "failed")
        self.assertIn("quota", self.doc.error_message)

    def test_malformed_llm_json_fails_with_actionable_message(self):
        from app.services.llm import LLMError

        def malformed(system, user):
            raise LLMError("LLM did not return valid JSON: Expecting value")

        self._run_pipeline(responder=malformed)
        self.assertEqual(self.doc.status, "failed")
        self.assertIn("valid JSON", self.doc.error_message)

    def test_daily_quota_fails_with_specific_reason(self):
        """A per-DAILY-token 429 must surface its real reason (not a generic
        'provider failed'), so the user knows it's an account/day limit."""
        from app.services.llm import LLMError

        def daily(system, user):
            raise LLMError(
                "Groq daily token quota is exhausted for this API key. The "
                "daily window resets later — try again then.",
                transient=False, rate_limit_kind="daily",
            )

        self._run_pipeline(responder=daily)
        self.assertEqual(self.doc.status, "failed")
        self.assertIn("daily token quota", self.doc.error_message)

    def test_partial_daily_quota_preserves_summary_and_reports_missing(self):
        """If the daily quota runs out after Summary, the Summary is kept and the
        missing sections are named with the reason — nothing is fabricated."""
        from app.services.llm import LLMError

        def responder(system, user):
            if "executive_summary" in user:
                return {
                    "document_type": "Service Agreement",
                    "executive_summary": "A master service agreement.",
                    "plain_english_overview": "Payment, termination, liability, renewal.",
                }
            raise LLMError(
                "Groq daily token quota is exhausted for this API key.",
                transient=False, rate_limit_kind="daily",
            )

        self._run_pipeline(responder=responder)
        self.db.refresh(self.doc)

        # Partial success is still usable, but clearly flagged.
        self.assertEqual(self.doc.status, "ready", self.doc.error_message)
        self.assertIn("daily token quota", self.doc.error_message)

        # The Summary that succeeded is preserved.
        analysis = self.db.query(models.DocumentAnalysis).filter_by(
            document_id=self.doc.id
        ).first()
        self.assertEqual(analysis.executive_summary, "A master service agreement.")

        # The failed extraction stages produced no fabricated findings.
        self.assertEqual(
            self.db.query(models.Risk).filter_by(document_id=self.doc.id).count(), 0
        )
        self.assertEqual(
            self.db.query(models.Clause).filter_by(document_id=self.doc.id).count(), 0
        )
        self.assertEqual(
            self.db.query(models.Obligation).filter_by(document_id=self.doc.id).count(), 0
        )


if __name__ == "__main__":
    unittest.main()
