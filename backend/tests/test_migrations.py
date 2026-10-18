import os
import tempfile
import unittest

from sqlalchemy import create_engine, inspect, text

from app.migrations import run_migrations

OLD_SCHEMA = """
CREATE TABLE documents (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    filename VARCHAR NOT NULL,
    file_type VARCHAR NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    storage_path VARCHAR NOT NULL,
    status VARCHAR,
    error_message TEXT,
    page_count INTEGER,
    document_type VARCHAR,
    overall_risk_level VARCHAR,
    created_at DATETIME,
    updated_at DATETIME
);
CREATE TABLE risks (
    id VARCHAR PRIMARY KEY,
    document_id VARCHAR NOT NULL,
    level VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    description TEXT NOT NULL,
    why_it_matters TEXT NOT NULL,
    plain_explanation TEXT,
    page_number INTEGER,
    section_reference VARCHAR,
    source_chunk_id VARCHAR
);
CREATE TABLE clauses (
    id VARCHAR PRIMARY KEY,
    document_id VARCHAR NOT NULL,
    category VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    original_text TEXT,
    plain_explanation TEXT,
    page_number INTEGER,
    section_reference VARCHAR,
    source_chunk_id VARCHAR
);
CREATE TABLE obligations (
    id VARCHAR PRIMARY KEY,
    document_id VARCHAR NOT NULL,
    party_name VARCHAR NOT NULL,
    obligation_text TEXT NOT NULL,
    page_number INTEGER,
    section_reference VARCHAR,
    source_chunk_id VARCHAR
);
CREATE TABLE important_dates (
    id VARCHAR PRIMARY KEY,
    document_id VARCHAR NOT NULL,
    label VARCHAR NOT NULL,
    date_value VARCHAR,
    description TEXT,
    page_number INTEGER,
    source_chunk_id VARCHAR
);
INSERT INTO documents (id, user_id, filename, file_type, file_size_bytes, storage_path, status, document_type)
VALUES ('doc-1', 'user-1', 'old-contract.txt', 'txt', 10, '/tmp/x.txt', 'ready', 'NDA');
INSERT INTO risks (id, document_id, level, title, description, why_it_matters)
VALUES ('risk-1', 'doc-1', 'High', 'Legacy risk', 'desc', 'why');
INSERT INTO obligations (id, document_id, party_name, obligation_text)
VALUES ('obl-1', 'doc-1', 'Client', 'Legacy obligation from the old schema.');
"""


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="lexclarity-migration-")
        self.db_path = os.path.join(self.tmpdir, "old.db")
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        with self.engine.begin() as conn:
            for stmt in OLD_SCHEMA.strip().split(";"):
                if stmt.strip():
                    conn.execute(text(stmt))

    def tearDown(self):
        self.engine.dispose()

    def test_additive_migration_preserves_existing_rows(self):
        applied = run_migrations(self.engine)

        self.assertIn("risks.category", applied)
        self.assertIn("documents.ocr_used", applied)
        self.assertIn("obligations.task_status", applied)

        with self.engine.connect() as conn:
            doc_count = conn.execute(text("SELECT count(*) FROM documents")).scalar()
            risk_count = conn.execute(text("SELECT count(*) FROM risks")).scalar()
        self.assertEqual(doc_count, 1)
        self.assertEqual(risk_count, 1)

        inspector = inspect(self.engine)
        risk_cols = {c["name"] for c in inspector.get_columns("risks")}
        for col in ("category", "evidence_quote", "verification_status", "severity_rationale"):
            self.assertIn(col, risk_cols)

        # Defaults applied where specified
        with self.engine.connect() as conn:
            task_status = conn.execute(text("SELECT task_status FROM obligations")).scalar()
        self.assertEqual(task_status, "pending")

    def test_migrations_are_idempotent(self):
        first = run_migrations(self.engine)
        second = run_migrations(self.engine)
        self.assertTrue(first)
        self.assertEqual(second, [])

    def test_new_tables_created_by_create_all_then_migrated(self):
        from app.database import Base
        from app import models  # noqa: F401

        Base.metadata.create_all(bind=self.engine)
        applied = run_migrations(self.engine)
        # documents table existed (old schema) -> its new columns get added;
        # brand-new tables already have full schema -> no ALTER needed for them
        self.assertIn("documents.extraction_method", applied)
        tables = inspect(self.engine).get_table_names()
        self.assertIn("action_items", tables)
        self.assertIn("evaluation_runs", tables)


if __name__ == "__main__":
    unittest.main()
