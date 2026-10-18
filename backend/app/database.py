from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables, then apply additive column migrations for
    pre-existing databases. Called on app startup (SQLite/dev convenience).

    For Postgres in production, prefer Alembic migrations instead of
    create_all — see README > Database Setup.
    """
    from app import models  # noqa: F401 ensure models are registered
    Base.metadata.create_all(bind=engine)

    from app.migrations import run_migrations
    applied = run_migrations(engine)
    if applied:
        print(f"[lexclarity] applied {len(applied)} schema migration(s): {', '.join(applied)}")
