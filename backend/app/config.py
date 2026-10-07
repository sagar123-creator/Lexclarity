"""
Central application configuration.

Every external dependency (LLM provider, model name, storage paths, limits)
is controlled here via environment variables so the app can be reconfigured
without touching code. See .env.example for the full list.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    # --- App ---
    APP_NAME: str = "LexClarity"
    ENV: str = os.getenv("ENV", "development")

    # --- Database ---
    # Defaults to a local SQLite file so the project runs with zero setup.
    # In production, point this at Postgres, e.g.:
    #   postgresql+psycopg2://user:pass@host:5432/lexclarity
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'storage' / 'lexclarity.db'}"
    )

    # --- Vector store ---
    # "chroma" (local, default) or "pgvector" (production - uses DATABASE_URL)
    VECTOR_BACKEND: str = os.getenv("VECTOR_BACKEND", "chroma")
    CHROMA_PERSIST_DIR: str = os.getenv(
        "CHROMA_PERSIST_DIR", str(BASE_DIR / "storage" / "chroma")
    )

    # --- File storage ---
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", str(BASE_DIR / "storage" / "uploads"))
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "20"))
    ALLOWED_EXTENSIONS: set = {".pdf", ".docx", ".txt"}

    # --- Embeddings ---
    # Local sentence-transformers model by default -> no external API key
    # required for embeddings. Swap EMBEDDING_PROVIDER to "openai" to use an
    # API-based embedding model instead (requires EMBEDDING_API_KEY).
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "local")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", "")

    # --- LLM ---
    # LLM_PROVIDER: "ollama", "anthropic", "openai", or "gemini"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama").lower()
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen2.5:7b")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2000"))

    # --- Chunking ---
    CHUNK_SIZE_TOKENS: int = int(os.getenv("CHUNK_SIZE_TOKENS", "350"))
    CHUNK_OVERLAP_TOKENS: int = int(os.getenv("CHUNK_OVERLAP_TOKENS", "60"))

    # --- RAG retrieval ---
    RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "6"))
    RETRIEVAL_MIN_SIMILARITY: float = float(os.getenv("RETRIEVAL_MIN_SIMILARITY", "0.25"))

    # --- Auth (simplified demo auth; see README for production notes) ---
    DEMO_USER_ID: str = os.getenv("DEMO_USER_ID", "demo-user")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")

    # --- CORS ---
    FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    FRONTEND_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGINS",
            FRONTEND_ORIGIN,
        ).split(",")
        if origin.strip()
    ]


settings = Settings()

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
os.makedirs(BASE_DIR / "storage", exist_ok=True)
