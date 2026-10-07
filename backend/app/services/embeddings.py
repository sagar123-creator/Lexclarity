"""
Embedding generation.

Default provider is a local sentence-transformers model, which means the
whole RAG pipeline works out of the box with no external API key. Set
EMBEDDING_PROVIDER=openai (with EMBEDDING_API_KEY) to use an API-based
embedding model instead — swap in services/embeddings.py without touching
any caller.
"""
from functools import lru_cache

from app.config import settings


class EmbeddingError(Exception):
    pass


@lru_cache(maxsize=1)
def _get_local_model():
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as e:
        raise EmbeddingError(
            "sentence-transformers could not be loaded. Run `pip install "
            f"sentence-transformers` or switch EMBEDDING_PROVIDER. Details: {e}"
        ) from e
    return SentenceTransformer(settings.EMBEDDING_MODEL)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns one vector per input text."""
    if not texts:
        return []

    if settings.EMBEDDING_PROVIDER == "local":
        model = _get_local_model()
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]

    if settings.EMBEDDING_PROVIDER == "openai":
        if not settings.EMBEDDING_API_KEY:
            raise EmbeddingError("EMBEDDING_API_KEY is not set for the 'openai' embedding provider.")
        try:
            from openai import OpenAI
        except ImportError as e:
            raise EmbeddingError("openai package is not installed.") from e
        client = OpenAI(api_key=settings.EMBEDDING_API_KEY)
        resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
        return [item.embedding for item in resp.data]

    raise EmbeddingError(f"Unknown EMBEDDING_PROVIDER: {settings.EMBEDDING_PROVIDER}")


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
