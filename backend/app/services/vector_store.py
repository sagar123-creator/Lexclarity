"""
Vector store abstraction.

Two backends implement the same small interface (upsert_chunks, query,
delete_document):

  - ChromaVectorStore  (VECTOR_BACKEND=chroma, default): local, zero-config,
    persists to disk under storage/chroma. Best for development and demos.

  - PgVectorStore      (VECTOR_BACKEND=pgvector): stores embeddings in a
    Postgres table using the pgvector extension. Recommended for production
    since it keeps chunks + vectors in the same transactional store as the
    rest of the app data.

Callers (services/chatbot.py, services/summarizer.py) only depend on
`get_vector_store()` and the interface below, so the backend can be swapped
purely through the VECTOR_BACKEND env var.
"""
from dataclasses import dataclass
from typing import Protocol

from app.config import settings


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    similarity: float
    page_number: int | None = None
    section_heading: str | None = None


class VectorStore(Protocol):
    def upsert_chunks(self, document_id: str, chunk_ids: list[str], texts: list[str],
                       embeddings: list[list[float]], metadatas: list[dict]) -> None: ...

    def query(self, document_id: str, query_embedding: list[float], top_k: int,
              document_ids: list[str] | None = None) -> list[RetrievedChunk]: ...

    def delete_document(self, document_id: str) -> None: ...


class ChromaVectorStore:
    def __init__(self):
        import chromadb
        self.client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        self.collection = self.client.get_or_create_collection(
            name="lexclarity_chunks",
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_chunks(self, document_id, chunk_ids, texts, embeddings, metadatas):
        for m in metadatas:
            m["document_id"] = document_id
        self.collection.upsert(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

    def query(self, document_id, query_embedding, top_k, document_ids=None):
        if document_ids is not None:
            # Cross-document query: merge per-document results (robust across
            # Chroma versions and always respects the document allow-list).
            out: list[RetrievedChunk] = []
            for doc_id in document_ids:
                out.extend(self.query(doc_id, query_embedding, top_k, document_ids=None))
            out.sort(key=lambda r: r.similarity, reverse=True)
            return out[:top_k]

        try:
            result = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where={"document_id": document_id},
            )
        except Exception:  # noqa: BLE001 - e.g. "requested results > index size"
            # Retry with progressively smaller k so tiny documents still work.
            for k in range(max(1, top_k - 1), 0, -1):
                try:
                    result = self.collection.query(
                        query_embeddings=[query_embedding],
                        n_results=k,
                        where={"document_id": document_id},
                    )
                    break
                except Exception:  # noqa: BLE001
                    continue
            else:
                return []
        out: list[RetrievedChunk] = []
        if not result["ids"] or not result["ids"][0]:
            return out
        for i, chunk_id in enumerate(result["ids"][0]):
            distance = result["distances"][0][i]  # cosine distance, lower = more similar
            similarity = max(0.0, 1.0 - distance)
            meta = result["metadatas"][0][i] or {}
            out.append(RetrievedChunk(
                chunk_id=chunk_id,
                text=result["documents"][0][i],
                similarity=similarity,
                page_number=meta.get("page_number"),
                section_heading=meta.get("section_heading"),
            ))
        return out

    def delete_document(self, document_id):
        self.collection.delete(where={"document_id": document_id})


class PgVectorStore:
    """Stores embeddings in Postgres using the pgvector extension.

    Requires: `CREATE EXTENSION IF NOT EXISTS vector;` on the target database,
    and the `pgvector` python package. Uses DATABASE_URL for the connection.
    """

    def __init__(self):
        import psycopg2
        from app.config import settings as s
        self._psycopg2 = psycopg2
        self.conn = psycopg2.connect(s.DATABASE_URL.replace("postgresql+psycopg2", "postgresql"))
        self.conn.autocommit = True
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chunk_embeddings (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    page_number INTEGER,
                    section_heading TEXT,
                    embedding vector(384)
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS chunk_embeddings_document_id_idx
                ON chunk_embeddings (document_id);
            """)

    def upsert_chunks(self, document_id, chunk_ids, texts, embeddings, metadatas):
        with self.conn.cursor() as cur:
            for cid, text, emb, meta in zip(chunk_ids, texts, embeddings, metadatas):
                cur.execute(
                    """
                    INSERT INTO chunk_embeddings (chunk_id, document_id, text, page_number, section_heading, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        text = EXCLUDED.text, embedding = EXCLUDED.embedding
                    """,
                    (cid, document_id, text, meta.get("page_number"), meta.get("section_heading"), emb),
                )

    def query(self, document_id, query_embedding, top_k, document_ids=None):
        if document_ids is not None:
            out: list[RetrievedChunk] = []
            for doc_id in document_ids:
                out.extend(self.query(doc_id, query_embedding, top_k, document_ids=None))
            out.sort(key=lambda r: r.similarity, reverse=True)
            return out[:top_k]
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT chunk_id, text, page_number, section_heading,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM chunk_embeddings
                WHERE document_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, document_id, query_embedding, top_k),
            )
            rows = cur.fetchall()
        return [
            RetrievedChunk(chunk_id=r[0], text=r[1], page_number=r[2], section_heading=r[3], similarity=float(r[4]))
            for r in rows
        ]

    def delete_document(self, document_id):
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM chunk_embeddings WHERE document_id = %s", (document_id,))


_store_instance = None


def get_vector_store() -> VectorStore:
    global _store_instance
    if _store_instance is None:
        if settings.VECTOR_BACKEND == "pgvector":
            _store_instance = PgVectorStore()
        else:
            _store_instance = ChromaVectorStore()
    return _store_instance
