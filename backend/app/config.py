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
    # LLM_PROVIDER: "gemini", "groq", "ollama", "anthropic", or "openai"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini").lower()
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-3.6-flash")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2000"))
    # Transient provider failures (5xx, rate limits, timeouts) are retried
    # this many times with exponential backoff starting at LLM_RETRY_BACKOFF_SECONDS.
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "3"))
    LLM_RETRY_BACKOFF_SECONDS: float = float(os.getenv("LLM_RETRY_BACKOFF_SECONDS", "1.5"))
    # Rate-limit (429 / token-quota) errors only clear when the provider's
    # rolling window rolls over (~60s), so they get a longer dedicated backoff
    # and more attempts than ordinary 5xx/timeout transients. This is what lets
    # a small free-tier tokens-per-minute budget (e.g. Groq's 8k TPM) survive a
    # back-to-back multi-stage pipeline instead of failing after ~10s of retries.
    LLM_RATE_LIMIT_BACKOFF_SECONDS: float = float(
        os.getenv("LLM_RATE_LIMIT_BACKOFF_SECONDS", "12.0")
    )
    LLM_RATE_LIMIT_BACKOFF_MAX_SECONDS: float = float(
        os.getenv("LLM_RATE_LIMIT_BACKOFF_MAX_SECONDS", "45.0")
    )
    LLM_RATE_LIMIT_RETRIES: int = int(os.getenv("LLM_RATE_LIMIT_RETRIES", "5"))
    # Client-side pacing against the provider's tokens-per-minute budget.
    # 0 disables throttling. Groq's free tier meters ~8000 tokens/min, so we
    # pace just under that to avoid 429s entirely instead of retrying after
    # them. Set to your plan's TPM (or 0 for local/Ollama).
    LLM_TOKEN_BUDGET_PER_MINUTE: float = float(os.getenv("LLM_TOKEN_BUDGET_PER_MINUTE", "7000"))

    # --- Chunking ---
    CHUNK_SIZE_TOKENS: int = int(os.getenv("CHUNK_SIZE_TOKENS", "350"))
    CHUNK_OVERLAP_TOKENS: int = int(os.getenv("CHUNK_OVERLAP_TOKENS", "60"))

    # --- RAG retrieval ---
    RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "6"))
    RETRIEVAL_MIN_SIMILARITY: float = float(os.getenv("RETRIEVAL_MIN_SIMILARITY", "0.25"))
    # Safety net below the strict bar: passages in this band are still handed to
    # the model (which must reply "not_found" when they don't answer). Without
    # it, short/single-chunk documents rarely clear 0.25 and every question
    # falls back to "not found" even when the answer is in the text.
    RETRIEVAL_MIN_SIMILARITY_FLOOR: float = float(
        os.getenv("RETRIEVAL_MIN_SIMILARITY_FLOOR", "0.10")
    )

    # --- OCR (optional fallback for scanned PDFs) ---
    OCR_ENABLED: bool = os.getenv("OCR_ENABLED", "true").lower() in ("1", "true", "yes")
    OCR_LANG: str = os.getenv("OCR_LANG", "eng")

    # --- Trust & verification engine ---
    # VERIFIER_PROVIDER: "auto" (NLI model if loadable, else LLM), "nli", "llm", "off"
    VERIFIER_PROVIDER: str = os.getenv("VERIFIER_PROVIDER", "auto").lower()
    VERIFIER_NLI_MODEL: str = os.getenv("VERIFIER_NLI_MODEL", "cross-encoder/nli-MiniLM2-L6-H768")
    # Minimum retrieval similarity before a passage may be used as evidence.
    VERIFICATION_MIN_SIMILARITY: float = float(os.getenv("VERIFICATION_MIN_SIMILARITY", "0.20"))
    # A claim's supporting passage must match at least this well for "supported".
    VERIFICATION_SUPPORT_THRESHOLD: float = float(os.getenv("VERIFICATION_SUPPORT_THRESHOLD", "0.35"))

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
