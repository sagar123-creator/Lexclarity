import unittest
from unittest.mock import patch

from app import models
from app.services.workspace_service import search_workspace, workspace_documents

from tests.fakes import DatabaseTestCase, FakeVectorStore, fake_retrieval, fake_llm


class WorkspaceIsolationTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.alice = self.make_user("alice")
        self.bob = self.make_user("bob")
        self.doc_a = self.make_document(user_id=self.alice.id, filename="alice-contract.txt")
        self.doc_b = self.make_document(user_id=self.bob.id, filename="bob-secret.txt")
        self.chunk_a = self.add_chunk(self.doc_a, "Alice's NDA: confidentiality survives for five years after termination.")
        self.chunk_b = self.add_chunk(self.doc_b, "Bob's salary is one million dollars per year.")

        self.ws_alice = models.Workspace(user_id=self.alice.id, name="Alice case")
        self.ws_bob = models.Workspace(user_id=self.bob.id, name="Bob case")
        self.db.add_all([self.ws_alice, self.ws_bob])
        self.db.commit()
        for ws, doc in ((self.ws_alice, self.doc_a), (self.ws_bob, self.doc_b)):
            self.db.add(models.WorkspaceDocument(workspace_id=ws.id, document_id=doc.id))
        self.db.commit()

        # One shared fake store containing both users' documents — the point
        # of the test is that scoping happens in the query, not the storage.
        self.store = FakeVectorStore()
        self.store.upsert_chunks(
            document_id=self.doc_a.id, chunk_ids=[self.chunk_a.id],
            texts=[self.chunk_a.text], embeddings=[None],
            metadatas=[{"page_number": 1, "section_heading": "NDA"}],
        )
        self.store.upsert_chunks(
            document_id=self.doc_b.id, chunk_ids=[self.chunk_b.id],
            texts=[self.chunk_b.text], embeddings=[None],
            metadatas=[{"page_number": 9, "section_heading": None}],
        )

    def test_workspace_documents_only_contains_members(self):
        ids = [d.id for d in workspace_documents(self.db, self.ws_alice)]
        self.assertEqual(ids, [self.doc_a.id])

    def test_cross_document_search_never_returns_other_workspace_content(self):
        with fake_retrieval(self.store), fake_llm(lambda s, u: {
            "confidence": "answered",
            "answer": "Alice's NDA states confidentiality survives five years.",
            "citations": [{"document_id": self.doc_a.id, "chunk_id": self.chunk_a.id, "page_number": 1}],
            "conflicts": [],
        }):
            result = search_workspace(self.db, self.ws_alice, "confidentiality survives five years")

        self.assertNotIn("million", result["answer"].lower())
        self.assertEqual(len(result["citations"]), 1)
        self.assertEqual(result["citations"][0]["document_id"], self.doc_a.id)
        self.assertEqual(result["citations"][0]["document_name"], "alice-contract.txt")
        # Bob's chunk was never retrievable from Alice's workspace scope
        self.assertTrue(all(c["chunk_id"] != self.chunk_b.id for c in result["citations"]))

    def test_injected_foreign_citation_is_dropped(self):
        """Even if the LLM cites a chunk outside the workspace, it is dropped."""
        with fake_retrieval(self.store), fake_llm(lambda s, u: {
            "confidence": "answered",
            "answer": "Some answer.",
            "citations": [{"document_id": self.doc_b.id, "chunk_id": self.chunk_b.id, "page_number": 9}],
            "conflicts": [],
        }):
            result = search_workspace(self.db, self.ws_alice, "confidentiality survives five years")
        self.assertEqual(result["citations"], [])

    def test_search_reports_not_found_when_nothing_relevant(self):
        with fake_retrieval(self.store), fake_llm([]):
            result = search_workspace(self.db, self.ws_alice, "quantum tunnelling lizards")
        self.assertEqual(result["confidence"], "not_found")
        self.assertEqual(result["citations"], [])

    def test_api_blocks_foreign_workspace_access(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import workspaces as ws_api
        from app.database import get_db
        from unittest.mock import patch as fs_patch

        app = FastAPI()
        app.include_router(ws_api.router)

        def _db():
            s = self.TestSession()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_db] = _db
        client = TestClient(app)

        with fs_patch("app.config.settings.DEMO_USER_ID", "bob"):
            resp = client.get(f"/api/workspaces/{self.ws_alice.id}")
            self.assertEqual(resp.status_code, 403)

        with fs_patch("app.config.settings.DEMO_USER_ID", "bob"):
            resp = client.get(f"/api/workspaces/{self.ws_bob.id}")
            self.assertEqual(resp.status_code, 200)
            names = [d["filename"] for d in resp.json()["documents"]]
            self.assertEqual(names, ["bob-secret.txt"])

    def test_adding_foreign_document_to_workspace_rejected(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import workspaces as ws_api
        from app.database import get_db
        from unittest.mock import patch as fs_patch

        app = FastAPI()
        app.include_router(ws_api.router)

        def _db():
            s = self.TestSession()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_db] = _db
        client = TestClient(app)

        with fs_patch("app.config.settings.DEMO_USER_ID", "bob"):
            resp = client.post(
                f"/api/workspaces/{self.ws_bob.id}/documents",
                json={"document_id": self.doc_a.id},  # alice's document
            )
            self.assertEqual(resp.status_code, 403)


class ConflictAttributionTests(DatabaseTestCase):
    def test_conflicts_and_per_document_attribution_pass_through(self):
        user = self.make_user()
        d1 = self.make_document(user_id=user.id, filename="nda-v1.txt")
        d2 = self.make_document(user_id=user.id, filename="nda-v2.txt")
        c1 = self.add_chunk(d1, "Confidentiality obligations last five years after termination.")
        c2 = self.add_chunk(d2, "Confidentiality obligations last ten years after termination.")
        ws = models.Workspace(user_id=user.id, name="case")
        self.db.add(ws)
        self.db.commit()
        for d in (d1, d2):
            self.db.add(models.WorkspaceDocument(workspace_id=ws.id, document_id=d.id))
        self.db.commit()

        with fake_retrieval() as store:
            store.upsert_chunks(d1.id, [c1.id], [c1.text], [None], [{"page_number": 1, "section_heading": "Confidentiality"}])
            store.upsert_chunks(d2.id, [c2.id], [c2.text], [None], [{"page_number": 2, "section_heading": "Confidentiality"}])
            with fake_llm(lambda s, u: {
                "confidence": "answered",
                "answer": (
                    "nda-v1.txt says confidentiality obligations last five years, while "
                    "nda-v2.txt says ten years — the documents conflict on duration."
                ),
                "citations": [
                    {"document_id": d1.id, "chunk_id": c1.id, "page_number": 1},
                    {"document_id": d2.id, "chunk_id": c2.id, "page_number": 2},
                ],
                "conflicts": [{
                    "topic": "confidentiality duration",
                    "document_a": "nda-v1.txt", "statement_a": "five years",
                    "document_b": "nda-v2.txt", "statement_b": "ten years",
                }],
            }):
                result = search_workspace(self.db, ws, "confidentiality obligations last five years ten years")

        self.assertEqual(result["confidence"], "answered")
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(result["conflicts"][0]["document_b"], "nda-v2.txt")
        self.assertEqual(len(result["citations"]), 2)
        names = {c["document_name"] for c in result["citations"]}
        self.assertEqual(names, {"nda-v1.txt", "nda-v2.txt"})
        # Verification runs over the answer's claims
        self.assertIn(result["verification"]["overall"], {"supported", "contradicted", "insufficient", "needs_review"})


class TimelineAndObligationTests(DatabaseTestCase):
    def test_timeline_merges_dates_with_document_attribution(self):
        from app.services.workspace_service import cross_document_timeline, cross_document_obligations

        user = self.make_user()
        d1 = self.make_document(user_id=user.id, filename="a.txt")
        d2 = self.make_document(user_id=user.id, filename="b.txt")
        self.db.add(models.ImportantDate(
            document_id=d1.id, label="Start", normalized_date="2026-01-01",
            date_kind="explicit", extraction_status="normalized", page_number=1,
        ))
        self.db.add(models.ImportantDate(
            document_id=d2.id, label="Expiry", normalized_date="2025-06-01",
            date_kind="explicit", extraction_status="normalized", page_number=2,
        ))
        self.db.add(models.Obligation(
            document_id=d2.id, party_name="Provider", obligation_text="Deliver monthly report",
            task_status="pending", verification_status="supported",
        ))
        ws = models.Workspace(user_id=user.id, name="case")
        self.db.add(ws)
        self.db.commit()
        for d in (d1, d2):
            self.db.add(models.WorkspaceDocument(workspace_id=ws.id, document_id=d.id))
        self.db.commit()

        timeline = cross_document_timeline(self.db, ws)
        self.assertEqual([t["normalized_date"] for t in timeline], ["2025-06-01", "2026-01-01"])
        self.assertEqual({t["document_name"] for t in timeline}, {"a.txt", "b.txt"})

        obligations = cross_document_obligations(self.db, ws)
        self.assertEqual(len(obligations), 1)
        self.assertEqual(obligations[0]["document_name"], "b.txt")


if __name__ == "__main__":
    unittest.main()
