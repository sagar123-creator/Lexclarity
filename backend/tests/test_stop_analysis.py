"""Stop-processing coverage.

A stop request has to work in the two shapes it actually arrives in: a stale
"processing" row with no live run behind it (left over from a restart), and a
document whose run is genuinely active. It must never stop a document that has
already finished, and it must never let one user stop another's document.
"""
import unittest
from unittest.mock import patch

from app import models
from app.services import cancellation

from tests.fakes import DatabaseTestCase


class StopAnalysisApiTests(DatabaseTestCase):
    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import analysis as analysis_api
        from app.database import get_db

        app = FastAPI()
        app.include_router(analysis_api.router)

        def _override_db():
            db = self.TestSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _override_db
        return TestClient(app)

    def test_stale_processing_document_settles_immediately(self):
        """No live run means no boundary is coming — settle it in the request."""
        user = self.make_user("demo-user")
        doc = self.make_document(user_id=user.id, status="analyzing")

        with patch("app.config.settings.DEMO_USER_ID", "demo-user"):
            resp = self._client().post(f"/api/documents/{doc.id}/stop")

        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["status"], "stopped")
        self.db.refresh(doc)
        self.assertEqual(doc.status, "stopped")
        self.assertIn("stopped", (doc.error_message or "").lower())

    def test_finished_document_cannot_be_stopped(self):
        user = self.make_user("demo-user")
        doc = self.make_document(user_id=user.id, status="ready")

        with patch("app.config.settings.DEMO_USER_ID", "demo-user"):
            resp = self._client().post(f"/api/documents/{doc.id}/stop")

        self.assertEqual(resp.status_code, 409, resp.text)
        self.db.refresh(doc)
        self.assertEqual(doc.status, "ready")

    def test_stop_is_idempotent(self):
        user = self.make_user("demo-user")
        doc = self.make_document(user_id=user.id, status="embedding")

        with patch("app.config.settings.DEMO_USER_ID", "demo-user"):
            client = self._client()
            first = client.post(f"/api/documents/{doc.id}/stop")
            second = client.post(f"/api/documents/{doc.id}/stop")

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["status"], "stopped")

    def test_ownership_is_enforced(self):
        owner = self.make_user("owner")
        other = self.make_user("other")
        doc = self.make_document(user_id=owner.id, status="analyzing")

        with patch("app.config.settings.DEMO_USER_ID", "other"):
            resp = self._client().post(f"/api/documents/{doc.id}/stop")

        self.assertEqual(resp.status_code, 403, resp.text)
        self.db.refresh(doc)
        self.assertEqual(doc.status, "analyzing")

    def test_stopped_document_still_serves_its_partial_results(self):
        """Stopping must not hide what the completed sections already produced."""
        user = self.make_user("demo-user")
        doc = self.make_document(user_id=user.id, status="stopped")
        self.add_chunk(doc, "Client shall pay Provider within thirty days of invoice.")

        with patch("app.config.settings.DEMO_USER_ID", "demo-user"):
            client = self._client()
            summary = client.get(f"/api/documents/{doc.id}/summary")
            risks = client.get(f"/api/documents/{doc.id}/risks")

        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(risks.status_code, 200, risks.text)

    def test_new_run_clears_a_leftover_stop_request(self):
        """An explicitly (re)started run must not be killed by the previous stop."""
        user = self.make_user("demo-user")
        doc = self.make_document(user_id=user.id, status="stopped")
        cancellation.request_stop(doc.id)

        with patch("app.config.settings.DEMO_USER_ID", "demo-user"), patch(
            "app.api.analysis.process_document"
        ) as pipeline:
            resp = self._client().post(f"/api/documents/{doc.id}/analyze")

        try:
            self.assertEqual(resp.status_code, 200, resp.text)
            pipeline.assert_called_once()
            self.assertFalse(cancellation.stop_requested(doc.id))
        finally:
            cancellation.clear_stop(doc.id)

    def test_stop_flag_and_running_registry_round_trip(self):
        self.assertFalse(cancellation.is_running("doc-x"))
        cancellation.mark_running("doc-x")
        self.assertTrue(cancellation.is_running("doc-x"))
        cancellation.request_stop("doc-x")
        self.assertTrue(cancellation.stop_requested("doc-x"))
        cancellation.mark_finished("doc-x")
        cancellation.clear_stop("doc-x")
        self.assertFalse(cancellation.is_running("doc-x"))
        self.assertFalse(cancellation.stop_requested("doc-x"))


if __name__ == "__main__":
    unittest.main()
