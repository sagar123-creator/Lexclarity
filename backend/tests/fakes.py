"""
Shared test infrastructure: isolated SQLite database, fake vector store and
fake embedding/LLM layers so tests are deterministic and offline.

The fake vector store scores by keyword overlap between the "query text"
(returned by the fake embedder) and stored chunk text — good enough to
exercise retrieval filtering and citation plumbing.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base


def _tokenize(text: str) -> set[str]:
    return {t for t in "".join(c if c.isalnum() else " " for c in (text or "").lower()).split() if len(t) > 2}


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


class FakeVectorStore:
    """In-memory stand-in for Chroma; query() scores by keyword overlap."""

    def __init__(self):
        self.store: dict[str, list[dict]] = {}

    def upsert_chunks(self, document_id, chunk_ids, texts, embeddings, metadatas):
        bucket = self.store.setdefault(document_id, [])
        for cid, text, meta in zip(chunk_ids, texts, metadatas):
            bucket = [c for c in bucket if c["chunk_id"] != cid]
            bucket.append({
                "chunk_id": cid,
                "text": text,
                "page_number": meta.get("page_number"),
                "section_heading": meta.get("section_heading") or None,
            })
        self.store[document_id] = bucket

    def query(self, document_id, query_embedding, top_k, document_ids=None):
        from app.services.vector_store import RetrievedChunk

        docs = document_ids if document_ids is not None else ([document_id] if document_id else list(self.store))
        results = []
        for doc_id in docs:
            for c in self.store.get(doc_id, []):
                sim = _similarity(str(query_embedding), c["text"])
                results.append(RetrievedChunk(
                    chunk_id=c["chunk_id"],
                    text=c["text"],
                    similarity=sim,
                    page_number=c["page_number"],
                    section_heading=c["section_heading"],
                ))
        results.sort(key=lambda r: r.similarity, reverse=True)
        return results[:top_k]

    def delete_document(self, document_id):
        self.store.pop(document_id, None)


# Modules that bound their own imports of embed_query / get_vector_store.
_EMBED_MODULES = [
    "app.services.chatbot", "app.services.extractor", "app.services.risk_analyzer",
    "app.services.summarizer",
    "app.services.embeddings",
]
# Modules that bind get_vector_store into their own namespace via `from ... import`.
# `pipeline` is deliberately excluded: it calls `vector_store.get_vector_store()`
# (module-qualified), so patching the attribute on the shared vector_store module
# already redirects it. Patching a non-existent `pipeline.get_vector_store` raises.
_STORE_MODULES = [
    "app.services.chatbot", "app.services.extractor", "app.services.risk_analyzer",
    "app.services.summarizer",
    "app.services.missing_clauses", "app.services.vector_store",
]
_LLM_MODULES = [
    "app.services.chatbot", "app.services.extractor", "app.services.risk_analyzer",
    "app.services.summarizer", "app.services.missing_clauses", "app.services.generator",
    "app.services.negotiation", "app.services.comparator",
    "app.services.llm",
]


@contextmanager
def fake_retrieval(store: FakeVectorStore | None = None):
    """Patch embeddings + vector store everywhere they're referenced."""
    store = store or FakeVectorStore()
    patches = []
    for mod in _EMBED_MODULES:
        patches.append(patch(f"{mod}.embed_query", lambda text: text))
    for mod in _STORE_MODULES:
        patches.append(patch(f"{mod}.get_vector_store", lambda: store))
    # Batch embedding used by the pipeline: echo texts back as "vectors".
    patches.append(patch("app.services.embeddings.embed_texts", lambda texts: list(texts)))
    for p in patches:
        p.start()
    try:
        yield store
    finally:
        for p in patches:
            p.stop()


@contextmanager
def fake_llm(responses):
    """Patch complete_json in every service module.

    `responses` is a list consumed in order, or a callable receiving
    (system_prompt, user_prompt) and returning the value (or raising).
    """
    calls: list[tuple[str, str]] = []

    def _fake(system_prompt: str, user_prompt: str, max_tokens=None):
        calls.append((system_prompt, user_prompt))
        if callable(responses):
            return responses(system_prompt, user_prompt)
        if not responses:
            raise AssertionError("fake_llm ran out of scripted responses")
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    patches = [patch(f"{mod}.complete_json", _fake) for mod in _LLM_MODULES]
    for p in patches:
        p.start()
    try:
        yield calls
    finally:
        for p in patches:
            p.stop()


class DatabaseTestCase(unittest.TestCase):
    """Base class giving each test class an isolated SQLite database."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="lexclarity-test-")
        cls._db_path = os.path.join(cls._tmpdir, "test.db")
        cls.test_engine = create_engine(
            f"sqlite:///{cls._db_path}", connect_args={"check_same_thread": False}
        )
        cls.TestSession = sessionmaker(autocommit=False, autoflush=False, bind=cls.test_engine)

        cls._patches = [
            patch("app.database.engine", cls.test_engine),
            patch("app.database.SessionLocal", cls.TestSession),
            # Tests must never trigger a real NLI model download or LLM call.
            # Each test that exercises verification patches semantic_verdict
            # directly; everything else runs deterministic-only.
            patch("app.config.settings.VERIFIER_PROVIDER", "off"),
            patch("app.services.verification.settings.VERIFIER_PROVIDER", "off"),
        ]
        for p in cls._patches:
            p.start()

        # Importing the models registers every table on Base.metadata — without
        # this, create_all() silently creates nothing when a test module doesn't
        # happen to import app.models first.
        import app.models  # noqa: F401

        Base.metadata.create_all(bind=cls.test_engine)

    @classmethod
    def tearDownClass(cls):
        for p in cls._patches:
            p.stop()
        cls.test_engine.dispose()

    def setUp(self):
        super().setUp()
        Base.metadata.drop_all(bind=self.test_engine)
        Base.metadata.create_all(bind=self.test_engine)
        self.db = self.TestSession()

    def tearDown(self):
        self.db.close()
        super().tearDown()

    # --- helpers ---
    def make_user(self, user_id="user-1"):
        from app import models
        user = models.User(id=user_id, email=f"{user_id}@test.local", name=user_id)
        self.db.add(user)
        self.db.commit()
        return user

    def make_document(self, user_id="user-1", filename="contract.txt", status="ready"):
        from app import models
        doc = models.Document(
            user_id=user_id, filename=filename, file_type="txt",
            file_size_bytes=100, storage_path="/tmp/x.txt", status=status,
            document_type="Service Agreement",
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def add_chunk(self, doc, text, page=1, section=None):
        from app import models
        chunk = models.DocumentChunk(
            document_id=doc.id, chunk_index=0, page_number=page,
            section_heading=section, text=text,
        )
        self.db.add(chunk)
        self.db.commit()
        self.db.refresh(chunk)
        return chunk

    def add_page(self, doc, text, page=1, ocr=False):
        from app import models
        row = models.DocumentPage(document_id=doc.id, page_number=page, text=text, ocr_used=ocr)
        self.db.add(row)
        self.db.commit()
        return row
