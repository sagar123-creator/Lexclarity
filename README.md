# LexClarity

**AI-powered legal document understanding.**
*Understand Legal Documents. Clearly.*

LexClarity is a full-stack web application that analyzes legal documents (PDF, DOCX, TXT)
and produces a structured breakdown — executive summary, document type, parties,
obligations, key dates, key clauses, and a risk analysis — then lets you ask questions
about the document through a Retrieval-Augmented-Generation (RAG) chatbot that answers
**only** from the uploaded text and cites its sources.

---

## 1. Features

- **Document upload** — drag-and-drop or browse, for PDF / DOCX / TXT (up to 20MB by default)
- **Real processing pipeline** — extract → clean → chunk → embed → store → analyze
- **Executive summary & document classification** (Employment Agreement, NDA, Lease, etc.)
- **Parties & obligations** — who's involved, and what each party must do
- **Key dates & deadlines** — start/end dates, renewal windows, notice periods, payment terms
- **Key clause extraction** — Termination, Payment, Confidentiality, Liability,
  Indemnification, IP, Non-compete, Dispute Resolution, Governing Law, Renewal, Penalties
- **Risk analysis** — High / Medium / Low risk items, each with a plain-English
  explanation and a source citation, using deliberately hedged, non-definitive language
- **"Explain Simply"** — every clause and risk includes a plain-English translation
- **Ask LexClarity** — a RAG chatbot with conversation memory, suggested questions,
  and page/section citations for every answer. It explicitly says *"I couldn't find this
  information in the uploaded document"* when the document doesn't contain an answer,
  rather than guessing.
- **Ownership isolation** — every document and chat request is scoped to its owner
- **Legal disclaimer** shown throughout the app

---

## 2. Architecture

```
┌─────────────┐      HTTP/JSON       ┌──────────────────┐
│   Next.js   │ ───────────────────▶ │     FastAPI       │
│  Frontend   │ ◀─────────────────── │     Backend        │
└─────────────┘                      └────────┬──────────┘
                                               │
                     ┌─────────────────────────┼─────────────────────────┐
                     ▼                         ▼                         ▼
              ┌─────────────┐           ┌─────────────┐           ┌─────────────┐
              │  PostgreSQL │           │  Vector DB   │           │  LLM API     │
              │  / SQLite   │           │ Chroma /     │           │ Anthropic /  │
              │ (structured │           │ pgvector     │           │ OpenAI       │
              │   data)     │           │ (embeddings) │           │ (generation) │
              └─────────────┘           └─────────────┘           └─────────────┘
```

### Processing pipeline (`app/services/pipeline.py`)

```
Upload Document
      │
      ▼
Extract Text        (document_parser.py — pypdf / python-docx / plain text, page-aware)
      │
      ▼
Clean Text           (utils/text_cleaning.py — whitespace, hyphenation, dehyphenation)
      │
      ▼
Split into Sentences  (utils/text_cleaning.py — legal-abbreviation-aware splitter)
      │
      ▼
Create Chunks         (chunking.py — sentence-packed, token-budgeted, with overlap
      │                and section-heading + page-number metadata attached)
      ▼
Generate Embeddings   (embeddings.py — local sentence-transformers by default)
      │
      ▼
Store in Vector DB    (vector_store.py — Chroma or pgvector, filtered by document_id)
      │
      ▼
Analyze Document       ┌─ Generate Summary        (summarizer.py)
      │                ├─ Extract Clauses         (extractor.py)
      │                ├─ Identify Risks          (risk_analyzer.py)
      │                ├─ Extract Obligations     (extractor.py)
      │                ├─ Extract Dates           (extractor.py)
      │                └─ Extract Entities        (extractor.py)
      ▼
Ready for Chat
```

Document status moves through `uploaded → extracting → chunking → embedding →
analyzing → ready` (or `failed`), and the frontend polls `GET /api/documents/{id}`
to show live progress.

### RAG chatbot flow (`app/services/chatbot.py`)

```
User question
      │
      ▼
Embed question (same embedding model as documents)
      │
      ▼
Semantic search — vector store, filtered to this document_id only
      │
      ▼
Keep chunks above RETRIEVAL_MIN_SIMILARITY, capped at RETRIEVAL_TOP_K
      │
      ├── nothing clears the bar ──▶ return "I couldn't find this information
      │                               in the uploaded document." (no LLM call —
      │                               this is the anti-hallucination guardrail)
      ▼
Build prompt: retrieved chunks + recent conversation history
      │
      ▼
LLM answers ONLY from the provided excerpts, returns structured JSON:
  { confidence, answer, citations: [{page_number, section, chunk_id}] }
      │
      ▼
Citations enriched with source snippets and returned to the frontend,
rendered as clickable "Source: Page N — Section" chips under the answer
```

This is why the document is never sent to the LLM in full: every LLM call —
summarization, extraction, risk analysis, and chat — is grounded in a small,
semantically-retrieved slice of the document, not the whole thing.

---

## 3. Tech Stack

| Layer            | Technology                                                   |
|-------------------|--------------------------------------------------------------|
| Frontend          | Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS |
| Backend           | FastAPI (Python), SQLAlchemy                                 |
| Database          | PostgreSQL (production) or SQLite (zero-config default)      |
| Vector store      | ChromaDB (default, local) or PostgreSQL + pgvector           |
| Embeddings        | sentence-transformers `all-MiniLM-L6-v2` (local, default), swappable to OpenAI embeddings |
| LLM               | Anthropic Claude (default) or OpenAI, swappable via env vars |
| Document parsing  | pypdf, python-docx                                            |

Every provider (LLM, embeddings, vector store, database) is swapped purely through
environment variables — no code changes required. See `.env.example`.

---

## 4. Folder Structure

```
lexclarity/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, startup, error handling
│   │   ├── config.py                # All settings, loaded from env vars
│   │   ├── database.py              # SQLAlchemy engine/session
│   │   ├── models.py                # ORM models (full schema)
│   │   ├── schemas.py               # Pydantic request/response models
│   │   ├── api/
│   │   │   ├── auth.py              # Simplified demo auth + user resolution
│   │   │   ├── upload.py            # POST /upload, GET /documents, ownership checks
│   │   │   ├── analysis.py          # summary / risks / clauses endpoints
│   │   │   └── chat.py              # RAG chat endpoint + conversation history
│   │   ├── services/
│   │   │   ├── document_parser.py   # PDF/DOCX/TXT extraction, page-aware
│   │   │   ├── chunking.py          # Sentence-aware chunking with overlap
│   │   │   ├── embeddings.py        # Pluggable embedding provider
│   │   │   ├── vector_store.py      # Chroma / pgvector backends
│   │   │   ├── llm.py               # Pluggable LLM provider (Anthropic/OpenAI)
│   │   │   ├── summarizer.py        # Executive summary + doc classification
│   │   │   ├── extractor.py         # Entities, obligations, dates, clauses
│   │   │   ├── risk_analyzer.py     # Risk detection with hedged language
│   │   │   ├── chatbot.py           # RAG question-answering + citations
│   │   │   └── pipeline.py          # Orchestrates the full pipeline
│   │   └── utils/
│   │       ├── text_cleaning.py     # Cleaning, sentence splitting, heading detection
│   │       └── file_validation.py   # Extension/size validation, filename sanitization
│   ├── sample_documents/
│   │   └── sample_service_agreement.txt
│   ├── requirements.txt
│   └── .env.example
│
└── frontend/
    ├── app/
    │   ├── page.tsx                 # Landing page
    │   ├── upload/page.tsx          # Upload + live processing status
    │   ├── dashboard/page.tsx       # Document list
    │   └── documents/[id]/page.tsx  # Analysis page (tabs: Overview/Risks/Clauses/Chat)
    ├── components/
    │   ├── upload/                  # Dropzone, processing stepper
    │   ├── dashboard/                # Document cards
    │   ├── analysis/                 # Overview/Risks/Clauses tabs
    │   ├── chatbot/                  # ChatPanel (Ask LexClarity)
    │   ├── layout/                   # Header, disclaimer
    │   └── ui/                       # Badge, Card, Button, Tabs primitives
    ├── lib/api.ts                   # Typed API client
    ├── types/index.ts               # Shared TypeScript types
    └── .env.local.example
```

---

## 5. Installation

### Prerequisites
- Python 3.11 (required by the pinned ChromaDB/NumPy dependencies)
- Node.js 18+
- A Gemini, Anthropic, or OpenAI API key (for summarization, extraction, risk analysis, and chat)

### Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set LLM_PROVIDER=gemini and LLM_API_KEY=your-gemini-key

uvicorn app.main:app --reload --port 8000
```

On Windows, run the backend with the virtual environment's interpreter if
activation is unavailable:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

The backend will:
- Create a local SQLite database automatically (`storage/lexclarity.db`)
- Create a local Chroma vector store automatically (`storage/chroma/`)
- Download the local embedding model on first use (~80MB, one-time)

No database server or vector database setup is required for local development.

### Frontend setup

```bash
cd frontend
npm install
cp .env.local.example .env.local
# Edit .env.local if your backend isn't on http://localhost:8000

npm run dev
```

Visit **http://localhost:3000**.

---

## 6. Environment Variables

### Backend (`backend/.env`)

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./storage/lexclarity.db` | Postgres example: `postgresql+psycopg2://user:pass@localhost:5432/lexclarity` |
| `VECTOR_BACKEND` | `chroma` | `chroma` or `pgvector` |
| `CHROMA_PERSIST_DIR` | `./storage/chroma` | Local Chroma storage path |
| `UPLOAD_DIR` | `./storage/uploads` | Where uploaded files are stored |
| `MAX_FILE_SIZE_MB` | `20` | Max upload size |
| `EMBEDDING_PROVIDER` | `local` | `local` (sentence-transformers) or `openai` |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Local embedding model name |
| `EMBEDDING_API_KEY` | (empty) | Required only if `EMBEDDING_PROVIDER=openai` |
| `LLM_PROVIDER` | `anthropic` | `gemini`, `anthropic`, or `openai` |
| `LLM_API_KEY` | (empty) | **Required.** Your LLM provider API key |
| `LLM_MODEL` | `claude-sonnet-4-6` | Any model string your provider supports, such as `gemini-2.5-flash` |
| `CHUNK_SIZE_TOKENS` | `350` | Approx. words per chunk |
| `CHUNK_OVERLAP_TOKENS` | `60` | Overlap carried between chunks |
| `RETRIEVAL_TOP_K` | `6` | Chunks retrieved per question |
| `RETRIEVAL_MIN_SIMILARITY` | `0.25` | Similarity floor before the chatbot will answer |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | CORS allow-origin |

### Frontend (`frontend/.env.local`)

| Variable | Default |
|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` |

**Never commit `.env` or `.env.local` files.** Secrets are read only on the backend;
the frontend never sees `LLM_API_KEY` or `EMBEDDING_API_KEY`.

---

## 7. Database Setup

### Development (default): SQLite
No setup needed — the file is created automatically on first run.

### Production: PostgreSQL

```bash
createdb lexclarity
```

Set `DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/lexclarity` and
restart the backend — tables are created automatically on startup via
`Base.metadata.create_all()`. For a real production deployment, replace this with
[Alembic](https://alembic.sqlalchemy.org/) migrations instead of `create_all`.

### Production vector store: pgvector

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Then set `VECTOR_BACKEND=pgvector` — LexClarity will create its `chunk_embeddings`
table automatically using the same `DATABASE_URL`.

---

## 8. API Documentation

Interactive docs are auto-generated by FastAPI at **http://localhost:8000/docs**.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/documents/upload` | Upload a document (multipart/form-data, field `file`) |
| `GET` | `/api/documents` | List the current user's documents |
| `GET` | `/api/documents/{id}` | Get a document's status/metadata |
| `POST` | `/api/documents/{id}/analyze` | (Re-)run the processing pipeline |
| `GET` | `/api/documents/{id}/summary` | Executive summary, parties, obligations, dates |
| `GET` | `/api/documents/{id}/risks` | Risk analysis items |
| `GET` | `/api/documents/{id}/clauses` | Extracted key clauses |
| `POST` | `/api/documents/{id}/chat` | Ask a question (RAG) |
| `GET` | `/api/documents/{id}/conversations/{cid}` | Full chat history |

### Chat request/response example

```json
POST /api/documents/{document_id}/chat
{
  "document_id": "…",
  "message": "What is the termination notice period?",
  "conversation_id": null
}
```

```json
{
  "conversation_id": "…",
  "answer": "The agreement requires 90 days' prior written notice for termination for convenience.",
  "citations": [
    { "chunk_id": "…", "page_number": 1, "section_reference": "4. Termination", "snippet": "…" }
  ],
  "confidence": "answered"
}
```

Every endpoint requires an `X-User-Id` header in a real multi-user deployment; if
omitted, a demo user is used automatically so the app works out of the box (see
`app/api/auth.py` for the swap-in point for real auth).

---

## 9. How the Chatbot Works

See **Section 2 (Architecture) → RAG chatbot flow** above for the full flow. In short:

1. Nothing is hardcoded — every answer is generated live from retrieved chunks.
2. The vector search is always filtered to the current `document_id`, so one user's
   document is never used to answer another document's questions.
3. If retrieved-chunk similarity is below `RETRIEVAL_MIN_SIMILARITY`, the chatbot skips
   the LLM call entirely and returns "I couldn't find this information in the uploaded
   document." — this is the primary anti-hallucination mechanism.
4. The system prompt (`app/services/chatbot.py`) explicitly forbids inventing facts,
   requires citations, and requires the model to separate "what the document says" from
   "what it may mean" from "when to consult a lawyer."
5. Conversation history (last 6 turns) is included in the prompt so follow-up questions
   ("What happens if I don't give that notice?") retain context.

---

## 10. Troubleshooting

| Problem | Likely cause / fix |
|---|---|
| Upload succeeds but status stays `failed` with "LLM_API_KEY is not set" | Set `LLM_API_KEY` in `backend/.env` and restart the backend |
| "sentence-transformers is not installed" | Run `pip install -r requirements.txt` again — this installs the local embedding model |
| Scanned PDF fails with "No extractable text was found" | The PDF is likely an image scan; run OCR on it first, or upload a text-based PDF |
| CORS errors in the browser console | Ensure `FRONTEND_ORIGIN` in `backend/.env` matches your frontend URL exactly |
| Chat always says "I couldn't find this information" | Lower `RETRIEVAL_MIN_SIMILARITY` in `.env` (e.g. to `0.15`), or check the document actually finished processing (`status: ready`) |
| First upload is slow | The local embedding model downloads once (~80MB) on first use — subsequent runs are fast |
| `psycopg2` install fails | Install PostgreSQL client headers (`apt install libpq-dev` on Debian/Ubuntu) or use the default SQLite setup instead |

---

## 11. Try It Immediately

A sample agreement is included at `backend/sample_documents/sample_service_agreement.txt`
— a Master Service Agreement with payment terms, termination, confidentiality, liability,
IP, non-compete, and dispute resolution clauses. Upload it right after setup to see the
full pipeline run, then try asking:

- "What is the notice period for termination?"
- "Who owns the intellectual property created under this agreement?"
- "What happens if Service Provider misses the uptime commitment?"
- "Is there a cap on liability?"
- "What happens if I don't pay an invoice on time?"

---

## 12. Security Notes

- File uploads are validated by extension and size; filenames are sanitized before
  being written to disk.
- Every document-scoped endpoint re-verifies `document.user_id == current_user.id`
  before returning any data (`app/api/upload.py::_get_owned_document`).
- API keys live only in backend environment variables and are never sent to the frontend.
- The global exception handler in `main.py` returns a generic message instead of leaking
  stack traces.
- The demo auth (`X-User-Id` header, defaulting to a fixed demo user) is intentionally
  simple for an MVP — replace `app/api/auth.py::get_current_user` with real session/JWT
  verification before any production deployment. Because ownership checks already flow
  through this one function, that swap doesn't require touching any other file.

---

## 13. Future Improvements

- Real authentication (JWT/session-based) and multi-user account management
- OCR fallback for scanned PDFs (e.g. via Tesseract)
- Reranking step (e.g. a cross-encoder) after initial vector retrieval for higher
  precision on longer documents
- Streaming chat responses (SSE) instead of request/response
- Document comparison (diff two versions of a contract)
- Exportable PDF/Word report of the full analysis
- Multi-document chat ("compare these two NDAs")
- Alembic migrations for schema changes in production
- Rate limiting and per-user upload quotas

---

## Disclaimer

**LexClarity is an AI-powered document analysis tool and does not provide legal advice.**
Its analysis may contain errors or omissions. Important legal decisions should be
reviewed with a qualified legal professional.
