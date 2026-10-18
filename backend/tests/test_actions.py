import unittest
from datetime import datetime, timedelta

from app import models
from app.services import action_center

from tests.fakes import DatabaseTestCase


class GenerateActionItemsTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.doc = self.make_document(user_id=self.user.id)

    def _add_risk(self, level="High", status="supported", title="Unlimited liability"):
        risk = models.Risk(
            document_id=self.doc.id, level=level, title=title,
            description="desc", why_it_matters="why",
            category="unlimited_liability",
            evidence_quote="quote text", page_number=2,
            suggested_action="Negotiate a cap.",
            severity_rationale="base level + escalation",
            verification_status=status,
        )
        self.db.add(risk)
        self.db.commit()
        self.db.refresh(risk)
        return risk

    def test_creates_action_with_evidence_and_priority_reason(self):
        risk = self._add_risk()
        created = action_center.generate_action_items(self.db, self.doc)
        self.assertEqual(len(created), 1)
        action = created[0]
        self.assertEqual(action.source_type, "risk")
        self.assertEqual(action.source_id, risk.id)
        self.assertEqual(action.priority, "high")  # High(3) + evidence verified(1) = 4
        self.assertTrue(action.priority_reason)
        self.assertEqual(action.evidence[0]["quote"], "quote text")
        self.assertEqual(action.status, "pending")
        self.assertEqual(action.decision, "undecided")
        self.assertIn("Negotiate a cap", action.suggested_action)

    def test_priority_reason_includes_evidence_status(self):
        self._add_risk(status="needs_review")
        action_center.generate_action_items(self.db, self.doc)
        action = self.db.query(models.ActionItem).first()
        self.assertIn("needs human review", action.priority_reason)

    def test_generation_is_idempotent(self):
        self._add_risk()
        first = action_center.generate_action_items(self.db, self.doc)
        second = action_center.generate_action_items(self.db, self.doc)
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)
        self.assertEqual(self.db.query(models.ActionItem).count(), 1)

    def test_urgent_deadline_raises_priority(self):
        upcoming = (datetime.utcnow() + timedelta(days=14)).date().isoformat()
        d = models.ImportantDate(
            document_id=self.doc.id, label="Non-renewal notice deadline",
            date_value="14 days from now", normalized_date=upcoming,
            date_kind="inferred", extraction_status="normalized",
            page_number=1,
        )
        self.db.add(d)
        self.db.commit()
        action_center.generate_action_items(self.db, self.doc)
        action = self.db.query(models.ActionItem).filter(models.ActionItem.source_type == "date").first()
        self.assertIsNotNone(action)
        self.assertIn("days left", action.priority_reason)
        self.assertEqual(action.priority, "high")  # base 2 + urgent 2 = 4 -> high
        self.assertIn("due within 30 days", action.priority_reason)

    def test_past_dates_do_not_become_actions(self):
        past = (datetime.utcnow() - timedelta(days=3)).date().isoformat()
        self.db.add(models.ImportantDate(
            document_id=self.doc.id, label="Old deadline", normalized_date=past,
            date_kind="explicit", extraction_status="normalized",
        ))
        self.db.commit()
        action_center.generate_action_items(self.db, self.doc)
        self.assertEqual(self.db.query(models.ActionItem).count(), 0)


class RecordDecisionTests(DatabaseTestCase):
    def test_decision_is_audit_logged(self):
        from app.services.action_center import record_decision

        user = self.make_user()
        doc = self.make_document(user_id=user.id)
        action = models.ActionItem(
            document_id=doc.id, source_type="risk", title="t", priority="medium",
        )
        self.db.add(action)
        self.db.commit()
        self.db.refresh(action)

        record_decision(self.db, user, action, "accepted", note="Looks good")
        self.db.refresh(action)
        self.assertEqual(action.decision, "accepted")

        log = self.db.query(models.AuditLog).filter(models.AuditLog.action == "action_item.decision").one()
        self.assertEqual(log.user_id, user.id)
        self.assertEqual(log.detail["decision"], "accepted")
        self.assertEqual(log.detail["note"], "Looks good")


class ActionApiTests(DatabaseTestCase):
    """API-level tests: status/decision validation and ownership."""

    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import actions as actions_api
        from app.database import get_db

        app = FastAPI()
        app.include_router(actions_api.router)

        def _override_db():
            db = self.TestSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _override_db
        return TestClient(app)

    def test_patch_status_and_decision(self):
        from unittest.mock import patch

        user = self.make_user("demo-user")
        doc = self.make_document(user_id=user.id)
        action = models.ActionItem(
            document_id=doc.id, source_type="risk", title="Review X", priority="high",
        )
        self.db.add(action)
        self.db.commit()
        self.db.refresh(action)

        client = self._client()
        with patch("app.config.settings.DEMO_USER_ID", "demo-user"):
            resp = client.patch(f"/api/actions/{action.id}", json={"status": "in_progress"})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["status"], "in_progress")

            resp = client.patch(f"/api/actions/{action.id}", json={"decision": "accepted", "note": "ok"})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["decision"], "accepted")

    def test_invalid_status_rejected(self):
        from unittest.mock import patch

        user = self.make_user("demo-user")
        doc = self.make_document(user_id=user.id)
        action = models.ActionItem(document_id=doc.id, source_type="risk", title="t", priority="low")
        self.db.add(action)
        self.db.commit()
        self.db.refresh(action)

        client = self._client()
        with patch("app.config.settings.DEMO_USER_ID", "demo-user"):
            resp = client.patch(f"/api/actions/{action.id}", json={"status": "weird"})
            self.assertEqual(resp.status_code, 422)

    def test_ownership_is_enforced(self):
        from unittest.mock import patch

        owner = self.make_user("owner")
        other = self.make_user("other")
        doc = self.make_document(user_id=owner.id)
        action = models.ActionItem(document_id=doc.id, source_type="risk", title="secret", priority="low")
        self.db.add(action)
        self.db.commit()
        self.db.refresh(action)

        client = self._client()
        with patch("app.config.settings.DEMO_USER_ID", "other"):
            resp = client.patch(f"/api/actions/{action.id}", json={"status": "completed"})
            self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
