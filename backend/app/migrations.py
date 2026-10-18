"""
Lightweight, safe schema migrations.

New tables are created by `Base.metadata.create_all()` (in database.init_db).
Columns added to *existing* tables after the fact are handled here: we inspect
the live schema and issue additive `ALTER TABLE ... ADD COLUMN` statements for
anything missing. All added columns are nullable (or have defaults), so this
preserves existing rows — including user data in a pre-existing SQLite file.

This is intentionally simple and idempotent. For production Postgres
deployments, prefer Alembic migrations (see README).
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text

logger = logging.getLogger("lexclarity.migrations")

# (table, column, sqlalchemy type string, [default]) — all nullable or defaulted.
ADDITIVE_COLUMNS: list[tuple[str, str, str, object | None]] = [
    # documents
    ("documents", "extraction_method", "VARCHAR", None),
    ("documents", "ocr_used", "BOOLEAN", False),
    # clauses
    ("clauses", "parties", "JSON", None),
    ("clauses", "rights_obligations", "TEXT", None),
    ("clauses", "concerns", "TEXT", None),
    ("clauses", "verification_status", "VARCHAR", None),
    ("clauses", "evidence_quote", "TEXT", None),
    ("clauses", "char_start", "INTEGER", None),
    ("clauses", "char_end", "INTEGER", None),
    # risks
    ("risks", "category", "VARCHAR", None),
    ("risks", "affected_party", "VARCHAR", None),
    ("risks", "evidence_quote", "TEXT", None),
    ("risks", "suggested_action", "TEXT", None),
    ("risks", "severity_rationale", "TEXT", None),
    ("risks", "verification_status", "VARCHAR", None),
    ("risks", "char_start", "INTEGER", None),
    ("risks", "char_end", "INTEGER", None),
    # obligations
    ("obligations", "deadline_text", "VARCHAR", None),
    ("obligations", "trigger_event", "VARCHAR", None),
    ("obligations", "conditions", "TEXT", None),
    ("obligations", "verification_status", "VARCHAR", None),
    ("obligations", "evidence_quote", "TEXT", None),
    ("obligations", "task_status", "VARCHAR", "pending"),
    # important_dates
    ("important_dates", "normalized_date", "VARCHAR", None),
    ("important_dates", "date_kind", "VARCHAR", None),
    ("important_dates", "extraction_status", "VARCHAR", None),
    ("important_dates", "evidence_quote", "TEXT", None),
    ("important_dates", "verification_status", "VARCHAR", None),
]


def run_migrations(engine) -> list[str]:
    """Apply additive column migrations. Returns the list of changes applied
    (empty list when the schema is already up to date)."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    applied: list[str] = []

    with engine.begin() as conn:
        for table, column, type_, default in ADDITIVE_COLUMNS:
            if table not in existing_tables:
                # Table created fresh by create_all with the full schema.
                continue
            cols = {c["name"] for c in inspector.get_columns(table)}
            if column in cols:
                continue
            default_sql = ""
            if default is not None:
                if isinstance(default, bool):
                    default_sql = f" DEFAULT {1 if default else 0}"
                elif isinstance(default, str):
                    escaped = default.replace("'", "''")
                    default_sql = f" DEFAULT '{escaped}'"
                else:
                    default_sql = f" DEFAULT {default}"
            stmt = f"ALTER TABLE {table} ADD COLUMN {column} {type_}{default_sql}"
            try:
                conn.execute(text(stmt))
                applied.append(f"{table}.{column}")
                logger.info("Applied migration: %s", stmt)
            except Exception as e:  # noqa: BLE001 - a raced/concurrent add is fine
                logger.warning("Could not apply %s: %s", stmt, e)
            # inspector caches; re-inspect after change
            inspector = inspect(engine)

    return applied
