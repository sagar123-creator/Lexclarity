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

LexClarity grew from a document summarizer into an evidence-grounded legal document
intelligence platform. The UI is split into two sections per document — **ANALYZE**
(understand what the document says) and **ACT** (decide and do something about it).

### ANALYZE
- **Document upload** — drag-and-drop or browse, for PDF / DOCX / TXT (up to 20MB by default)
- **Real processing pipeline** — extract → clean → chunk → embed → store → analyze
- **Executive summary & document classification** (Employment Agreement, NDA, Lease, etc.)
- **Parties & obligations** — who's involved, and what each party must do, with
  per-obligation task tracking (pending / in progress / completed)
- **Key dates & deadlines** — start/end dates, renewal windows, notice periods, payment
  terms; each date is labelled `explicit` vs `inferred` and `normalized` / `raw_only` / `uncertain`
- **Key clause extraction** — Termination, Payment, Confidentiality, Liability,
  Indemnification, IP, Non-compete, Dispute Resolution, Governing Law, Renewal, Penalties,
  each enriched with plain-English explanation, rights/obligations, and concerns
- **Risk analysis** — High / Medium / Low risk items, each with a plain-English
  explanation, a source citation, a **deterministic severity rationale**, and a suggested
  next step. Severity is never the LLM's say-so alone — see `risk_rules.py`.
- **Evidence viewer** — the exact stored page text behind every finding; citation chips
  are clickable and open a panel that highlights the cited passage (and warns when a quote
  can't be located). OCR-sourced pages are flagged.
- **Ask LexClarity** — a RAG chatbot with conversation memory, suggested questions,
  page/section citations for every answer, and per-citation verification (a citation whose
  source wasn't actually retrieved is shown with an explicit warning). It says
  *"I couldn't find this information in the uploaded document"* rather than guessing.
- **Verify a claim** — type any statement and get a deterministic trust verdict:
  `supported`, `contradicted`, `insufficient`, or `needs_review`, with the method
  (`deterministic` / `nli` / `llm`) and the evidence excerpt.

### ACT
- **Action Center** — concrete next steps derived from the document's findings, with
  explainable priority scoring, status (pending / in progress / completed) and decision
  (accepted / rejected / deferred) tracking. Nothing is ever sent or filed automatically.
- **Legal action plan** — an ordered, priority-grouped view of every action item.
- **Negotiation assistant** — pick a clause and get friendlier / more balanced proposed
  wording with rationale and talking points; original text is always preserved.
- **Document generator** — AI drafts for common legal letters/notices. Missing facts are
  left as `[PLACEHOLDER: …]` rather than invented; drafts are editable and exportable as
  Markdown.
- **Deadline tracker** — reminders from document dates plus manual ones; `inferred` dates
  are labelled. Reminders are internal only — no emails are sent.
- **Missing-clause checklist** — checks for clauses normally found in this document type.
  "Missing" means the text wasn't found, not a legal opinion that it's required.
- **Contract comparison** — clause-by-clause diff of two analyzed documents plus a risk
  profile delta; material term changes (amounts, notice periods) are called out even when
  wording barely changed. The summary describes textual differences only.

### Platform
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

**Stop processing.** Every card in a processing state offers *Stop processing*
(dashboard card, and the stepper on the upload page) → `POST /api/documents/{id}/stop`.
Stopping is cooperative: a run that is genuinely in flight settles as `stopped`
at its next stage boundary (an LLM call already under way finishes first), while
a row that only *looks* busy — left behind by a restart, no run behind it — is
settled immediately instead of waiting for a boundary that never comes.
Everything the completed stages wrote is kept: a `stopped` document stays
readable and chat-able (the page shows a banner over the partial results), and
**Resume analysis** re-runs only the sections that are still missing. The stop
flag and the "is a run live" registry live in-process (`app/services/cancellation.py`),
which is correct for the single-worker server here; a multi-worker deployment
would want a shared flag such as a `stop_requested` column on `documents`.

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
Prefer chunks above RETRIEVAL_MIN_SIMILARITY, capped at RETRIEVAL_TOP_K
      │
      ├── none clear the bar ──▶ keep the closest chunks above
      │                          RETRIEVAL_MIN_SIMILARITY_FLOOR (near-miss band:
      │                          local embeddings often score genuine matches low,
      │                          especially on short / single-chunk documents)
      │
      ├── none clear the floor either ──▶ return the "I couldn't find anything about
      │                                    that in this document…" refusal, which
      │                                    invites a document-related question
      │                                    (no LLM call — anti-hallucination guardrail)
      ▼
Build prompt: retrieved chunks + recent conversation history + the file's name
      │
      ▼
LLM answers ONLY from the provided excerpts, returns structured JSON:
  { confidence, answer, citations: [{page_number, section, chunk_id}] }
      │
      ▼
When the excerpts don't answer (or the question isn't about this document) the
model returns confidence "not_found" and its reply says the document doesn't
cover it + asks for a valid document question — it never guesses
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
| LLM               | Gemini (default), Groq, Anthropic, OpenAI, or local Ollama — swappable via env vars |
| Verification      | Deterministic matching + optional local NLI (`cross-encoder/nli-MiniLM2-L6-H768`) + LLM judge |
| Document parsing  | pypdf, python-docx; optional OCR via PyMuPDF + Tesseract |

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
│   │   ├── migrations.py            # Additive, idempotent schema upgrades
│   │   ├── api/
│   │   │   ├── auth.py              # Simplified demo auth + user resolution
│   │   │   ├── upload.py            # POST /upload, GET /documents, ownership checks
│   │   │   ├── analysis.py          # summary / risks / clauses endpoints
│   │   │   ├── chat.py              # RAG chat endpoint + conversation history
│   │   │   ├── evidence.py          # Page text + chunk retrieval
│   │   │   ├── verification.py      # Claim verification (trust engine)
│   │   │   ├── actions.py           # Action Center CRUD + generation
│   │   │   ├── plan.py              # Legal action plan
│   │   │   ├── negotiation.py       # Clause suggestions
│   │   │   ├── generator.py         # Draft generation / editing / export
│   │   │   ├── deadlines.py         # Reminders + obligation task status
│   │   │   ├── checklist.py         # Missing-clause checklist
│   │   │   └── compare.py           # Contract comparison
│   │   ├── services/
│   │   │   ├── document_parser.py   # PDF/DOCX/TXT extraction, page-aware, OCR fallback
│   │   │   ├── chunking.py          # Sentence-aware chunking with overlap
│   │   │   ├── embeddings.py        # Pluggable embedding provider
│   │   │   ├── vector_store.py      # Chroma / pgvector backends
│   │   │   ├── llm.py               # Pluggable LLM provider + transient retry/backoff
│   │   │   ├── summarizer.py        # Executive summary + doc classification
│   │   │   ├── extractor.py         # Entities, obligations, dates, clauses
│   │   │   ├── risk_analyzer.py     # Risk detection with hedged language
│   │   │   ├── risk_rules.py        # Deterministic severity rubric
│   │   │   ├── verification.py      # Trust engine (deterministic/NLI/LLM judge)
│   │   │   ├── action_center.py     # Priority scoring + action generation
│   │   │   ├── negotiation.py       # Clause rewrite suggestions
│   │   │   ├── generator.py         # Draft templates + placeholder invariant
│   │   │   ├── comparator.py        # Clause diff + risk delta
│   │   │   ├── missing_clauses.py   # Missing-clause checklist engine
│   │   │   ├── chatbot.py           # RAG question-answering + citations
│   │   │   └── pipeline.py          # Orchestrates the full pipeline (+ outage handling)
│   │   └── utils/
│   │       ├── text_cleaning.py     # Cleaning, sentence splitting, heading detection
│   │       └── file_validation.py   # Extension/size validation, filename sanitization
│   ├── tests/                       # unittest suite (108 tests)
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
    │   ├── documents/[id]/page.tsx  # ANALYZE + ACT tabs
    ├── components/
    │   ├── upload/                  # Dropzone, processing stepper
    │   ├── dashboard/               # Document cards
    │   ├── analysis/                # Summary/Obligations/Dates/Evidence/Risks/Clauses tabs
    │   ├── action/                  # Action Center/Plan/Negotiation/Generator/Deadlines/
    │   │                            #   Compliance/Comparison tabs
    │   ├── evidence/                # CitationChip, EvidencePanel, VerificationBadge
    │   ├── chatbot/                 # ChatPanel (Ask LexClarity)
    │   ├── layout/                  # Header, disclaimer, ANALYZE/ACT SectionNav
    │   └── ui/                      # Badge, Card, Button, Tabs primitives
    ├── lib/api.ts                   # Typed API client (all endpoints)
    ├── types/index.ts               # Shared TypeScript types
    └── .env.local.example
```

---

## 5. Installation

### Prerequisites
- Python 3.10+
- Node.js 18+
- A Gemini API key (for summarization, extraction, risk analysis, and chat)

### Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Add your Gemini API key to backend/.env as described below

uvicorn app.main:app --reload --port 8000
```

The backend will:
- Create a local SQLite database automatically (`storage/lexclarity.db`)
- Create a local Chroma vector store automatically (`storage/chroma/`)
- Download the local embedding model on first use (~80MB, one-time)

No database server or vector database setup is required for local development.

### Running LexClarity with Gemini

Gemini is the default LLM provider. Create a Google AI Studio account and API key at
https://aistudio.google.com/apikey, then set these values in `backend/.env`:

   ```dotenv
   LLM_PROVIDER=gemini
   LLM_API_KEY=YOUR_GEMINI_API_KEY
   LLM_MODEL=gemini-3.6-flash
   LLM_BASE_URL=
   LLM_MAX_TOKENS=2000
   ```

Start the backend:
   `.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000`
Start the frontend with `npm run dev`, upload a legal document, and verify its summary,
clauses, risks, faithfulness verification, and chatbot responses.

Groq, Anthropic, OpenAI, and the existing Ollama adapter remain available by setting `LLM_PROVIDER`,
`LLM_MODEL`, and the corresponding cloud `LLM_API_KEY`.

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
| `LLM_PROVIDER` | `gemini` | `gemini`, `groq`, `anthropic`, `openai`, or `ollama` |
| `LLM_API_KEY` | (empty) | Gemini API key, or the key required by the selected cloud provider |
| `LLM_MODEL` | `gemini-3.6-flash` | Any model string your provider supports |
| `LLM_BASE_URL` | (empty) | Optional provider base URL; used by OpenAI-compatible providers |
| `LLM_MAX_TOKENS` | `2000` | Max tokens per LLM completion |
| `LLM_MAX_RETRIES` | `3` | Retries for transient LLM failures (5xx / rate limit / timeout) |
| `LLM_RETRY_BACKOFF_SECONDS` | `1.5` | Base backoff; doubles per retry (1.5s → 3s → 6s …) |
| `LLM_RATE_LIMIT_BACKOFF_SECONDS` | `12.0` | Base backoff for rate-limit (429) retries; a provider `retry-after` hint is honoured when sent, plus bounded jitter |
| `LLM_RATE_LIMIT_BACKOFF_MAX_SECONDS` | `45.0` | Hard cap on any single rate-limit backoff wait |
| `LLM_RATE_LIMIT_RETRIES` | `5` | Attempts for *transient* (per-minute) rate limits before giving up |
| `LLM_TOKEN_BUDGET_PER_MINUTE` | `0` | Client-side tokens-per-minute pacing (0 = off). Groq's free tier meters ~8000 TPM |

> **Groq free-tier daily quota (TPD).** Beyond the ~8000 TPM window, Groq's free tier enforces a **tokens-per-day** quota (≈200k/day on `openai/gpt-oss-120b`). When it is hit, the API returns `429` with `code: rate_limit_exceeded`, `type: tokens`, and a `retry-after` of many minutes. LexClarity detects this *daily* dimension (vs. per-minute TPM or requests-per-minute RPM) and **fails fast** — it does not blind-retry for minutes, because a per-day quota cannot recover in a 45s backoff. Sections that already completed are **kept**, and the remaining stages are **skipped** and named in `error_message`. **Re-analyze resumes**: it retries *only* the sections named as missing (the ones that already worked are left untouched and cost nothing), so a retry under a scarce daily budget actually reaches them — pass `?full=true` to rebuild everything from scratch instead. A different API key, a higher tier, a model with its own quota (`LLM_MODEL` limits are per model), or a lower `LLM_TOKEN_BUDGET_PER_MINUTE` are the ways to get more headroom.
| `VERIFIER_PROVIDER` | `auto` | Trust engine: `auto`, `nli`, `llm`, or `off`. `auto` lazily loads a local NLI model and falls back to an LLM judge (labelled as non-proof) |
| `OCR_ENABLED` | `true` | Tesseract OCR fallback for scanned/image PDFs |
| `CHUNK_SIZE_TOKENS` | `350` | Approx. words per chunk |
| `CHUNK_OVERLAP_TOKENS` | `60` | Overlap carried between chunks |
| `RETRIEVAL_TOP_K` | `6` | Chunks retrieved per question |
| `RETRIEVAL_MIN_SIMILARITY` | `0.25` | Similarity bar above which a chunk is trusted outright |
| `RETRIEVAL_MIN_SIMILARITY_FLOOR` | `0.10` | Below-bar chunks still sent to the model, which must refuse if they don't answer |
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

### Schema migrations (additive)

New tables are created automatically by `Base.metadata.create_all()`. For **existing**
databases, `app/migrations.py` runs a set of additive, idempotent upgrades on startup
(`ALTER TABLE … ADD COLUMN` guarded by an inspector check), so upgrading an older
LexClarity database never drops or rewrites data. It is safe to restart repeatedly.

> **Note:** migration is additive-only by design. If you need to change an existing
> column's type or drop one, that is a destructive change and must be done manually —
> this project deliberately never does it automatically.

Key new tables/columns introduced by the intelligence platform: `document_pages`
(full page text — the evidence viewer's source of truth), `action_items`, `drafts`,
`clause_suggestions`, `reminders`, `checklist_items`, `comparisons`, plus
verification/evidence columns on
`risks`, `clauses`, `obligations`, and `important_dates`.

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
| `POST` | `/api/documents/{id}/analyze` | (Re-)run the processing pipeline. Resumes by default — only sections with no results are retried; `?full=true` rebuilds everything |
| `POST` | `/api/documents/{id}/stop` | Stop processing (cooperative: a live run settles at its next stage boundary, a stale row settles at once). Partial results are kept and remain readable |
| `GET` | `/api/documents/{id}/summary` | Executive summary, parties, obligations, dates |
| `GET` | `/api/documents/{id}/risks` | Risk analysis items |
| `GET` | `/api/documents/{id}/clauses` | Extracted key clauses |
| `POST` | `/api/documents/{id}/chat` | Ask a question (RAG) |
| `GET` | `/api/documents/{id}/conversations/{cid}` | Full chat history |
| `GET` | `/api/documents/{id}/pages` | All stored page text (evidence source of truth) |
| `GET` | `/api/documents/{id}/pages/{n}` | One page's text |
| `GET` | `/api/documents/{id}/chunks/{chunk_id}` | One retrieved chunk |
| `POST` | `/api/documents/{id}/verify-claim` | Deterministic claim verification (trust engine) |
| `GET` | `/api/documents/{id}/actions` | List action items |
| `POST` | `/api/documents/{id}/actions/generate` | (Re)generate action items from findings |
| `GET`/`PATCH` | `/api/actions/{action_id}` | Get / update an action (status, decision) |
| `GET` | `/api/documents/{id}/plan` | Ordered legal action plan |
| `GET` | `/api/templates` | Available draft templates |
| `POST` | `/api/documents/{id}/drafts` | Generate an AI draft (with placeholders) |
| `GET` | `/api/documents/{id}/drafts` | List drafts |
| `GET`/`PUT` | `/api/drafts/{draft_id}` | Get / edit a draft |
| `GET` | `/api/drafts/{draft_id}/export` | Export a draft as Markdown |
| `POST` | `/api/documents/{id}/negotiate` | Suggest edits for a clause |
| `GET` | `/api/documents/{id}/negotiate` | List saved suggestions |
| `GET`/`POST` | `/api/documents/{id}/reminders` | List / create deadline reminders |
| `PATCH`/`DELETE` | `/api/reminders/{reminder_id}` | Update / delete a reminder |
| `PATCH` | `/api/obligations/{id}` | Update an obligation's task status |
| `GET` | `/api/documents/{id}/checklist` | Missing-clause checklist results |
| `POST` | `/api/documents/{id}/checklist/run` | (Re)run the missing-clause checklist |
| `POST` | `/api/compare` | Compare two analyzed documents |
| `GET` | `/api/compare` / `/api/compare/{id}` | List / get comparisons |

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
3. Chunks above `RETRIEVAL_MIN_SIMILARITY` are trusted outright. If none clear that bar,
   the closest chunks above `RETRIEVAL_MIN_SIMILARITY_FLOOR` are still sent (local
   embeddings often score real matches below 0.25 on short documents); if nothing clears
   the floor either, the chatbot skips the LLM call and returns a refusal that invites a
   document-related question. That refusal path — plus the model's own "not_found"
   verdict — is the primary anti-hallucination mechanism.
4. The system prompt (`app/services/chatbot.py`) requires a direct, plain-English answer
   first (not a paste of the document text), forbids inventing facts, requires citations,
   and requires the model to separate "what the document says" from "what it may mean"
   from "when to consult a lawyer."
5. Conversation history (last 6 turns) is included in the prompt so follow-up questions
   ("What happens if I don't give that notice?") retain context.

---

## 10. Testing

### Backend (Python)

The backend has a `unittest` suite covering the pipeline, trust engine, risk rubric,
comparator, generator placeholder invariant, migrations, and more. Tests run
offline — they use an isolated temp SQLite database, a `FakeVectorStore`, and scripted
`fake_llm` responders, and they patch `VERIFIER_PROVIDER="off"` so no NLI model is ever
downloaded during tests.

```bash
cd backend
.\venv\Scripts\python.exe -m unittest discover -s tests -q    # Windows
python3 -m unittest discover -s tests -q                       # macOS/Linux
```

**Result: 108 tests, all passing (OK).**

> If you redirect output with `2>&1` in PowerShell, confirm the outcome with `$LASTEXITCODE`
> rather than the shell's "Exited with code" line, which can be misleading.

### Frontend (TypeScript)

There is no browser/unit test runner wired up for the frontend yet. Instead, correctness is
enforced by a strict typecheck and a production build, both of which pass clean:

```bash
cd frontend
npx tsc --noEmit     # typecheck — passes with 0 errors
npm run build        # production build — compiles and generates every route
```

### End-to-end smoke test

An end-to-end script uploads `sample_documents/sample_service_agreement.txt` and exercises
every major endpoint (summary, risks, clauses, pages, checklist, actions, plan, chat,
verify-claim, negotiate, drafts, compare). It requires a **working**
LLM API key — see the limitations note below.

---

## 11. Troubleshooting

| Problem | Likely cause / fix |
|---|---|
| Upload succeeds but status stays `failed` with "LLM_API_KEY is not set" | Set `LLM_API_KEY` in `backend/.env` and restart the backend |
| Document fails with "Gemini API quota or rate limit reached" | Your Gemini **free-tier** quota is exhausted (limit ~20 requests; resets after a few hours) or you hit a per-minute rate limit. Transient failures are retried automatically with backoff; persistent quota exhaustion needs a paid plan, a different key, or a different `LLM_PROVIDER`. |
| Document `failed` with a message listing several stages | The LLM provider was unreachable. Transient errors (5xx / rate limit / timeout) are retried with exponential backoff (`LLM_MAX_RETRIES`, `LLM_RETRY_BACKOFF_SECONDS`). If **all** stages fail, the document is marked failed with this actionable message; if only some fail, the document still reaches `ready` and the partial-failure note appears in `error_message`. |
| Document fails with "Groq daily token quota is exhausted" | Your Groq key hit the **tokens-per-day** (TPD) free-tier quota (~200k/day). This is an account/day limit, not a code bug — LexClarity fails fast (no blind retries), keeps completed sections, and names the skipped ones. Wait for the daily window to reset and **Re-analyze** (which retries only those missing sections), or switch `LLM_MODEL` — quotas are per model, so a sibling model has its own budget — or use a different key / higher tier. Check `console.groq.com` for your exact usage. |
| "sentence-transformers is not installed" | Run `pip install -r requirements.txt` again — this installs the local embedding model |
| Scanned PDF fails with "No extractable text was found" | Install OCR deps (`pip install pymupdf pytesseract` + the Tesseract binary) with `OCR_ENABLED=true`, or upload a text-based PDF |
| CORS errors in the browser console | Ensure `FRONTEND_ORIGINS` in `backend/.env` matches your frontend URL exactly |
| Chat always says "I couldn't find this information" | Lower `RETRIEVAL_MIN_SIMILARITY` in `.env` (e.g. to `0.15`) — or check `RETRIEVAL_MIN_SIMILARITY_FLOOR` isn't set above it — and check the document actually finished processing (`status: ready`) |
| First upload is slow | The local embedding model downloads once (~80MB) on first use — subsequent runs are fast |
| `psycopg2` install fails | Install PostgreSQL client headers (`apt install libpq-dev` on Debian/Ubuntu) or use the default SQLite setup instead |

---

## 12. Try It Immediately

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

## 13. Security Notes

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

## 14. Limitations (honest notes)

- **LLM availability.** Analysis, risk detection, clause enrichment, chat, negotiation, and
  draft generation all depend on a reachable LLM. With a Gemini **free-tier** key, sustained
  use hits a hard quota (~20 requests, reset after hours). Transient errors are retried with
  backoff, but quota exhaustion is not something retry can fix — use a paid plan or a
  different provider for production use. When the provider is down, documents fail with a
  clear, actionable message rather than silently producing empty results.
- **Severity is deterministic, not omniscient.** Risk severity comes from a documented
  keyword/phrase rubric (`risk_rules.py`), not the model's opinion. It will miss novel risks
  that don't match the rubric and is intentionally conservative — borderline items are
  flagged `needs_review` rather than asserted.
- **Verification has three tiers.** Deterministic text/value matching is authoritative;
  the local NLI model is a strong heuristic; the LLM judge is explicitly labelled as *not
  proof*. OCR-derived evidence degrades to `needs_review` because OCR can alter characters.
- **No automatic actions.** LexClarity drafts reminders, replies, and redlines but never
  sends, files, or emails anything. Every external action requires a human.
- **Drafts contain placeholders.** Missing facts are left as `[PLACEHOLDER: …]`. A draft is
  a starting point, not a finished legal document.
- **Demo auth.** Documents are scoped by an `X-User-Id` header (demo user by default). Swap
  `app/api/auth.py::get_current_user` for real session/JWT auth before production.
- **Frontend has no unit-test runner.** Correctness is enforced by strict typechecking and a
  clean production build; the backend carries the automated test suite (108 tests).

---

## 15. Future Improvements

- Real authentication (JWT/session-based) and multi-user account management
- Reranking step (e.g. a cross-encoder) after initial vector retrieval for higher
  precision on longer documents
- Streaming chat responses (SSE) instead of request/response
- Exportable PDF/Word report of the full analysis
- Alembic migrations for richer (non-additive) schema changes in production
- Rate limiting and per-user upload quotas
- Frontend unit tests (e.g. Vitest + Testing Library) alongside the backend suite

---

## Disclaimer

**LexClarity is an AI-powered document analysis tool and does not provide legal advice.**
Its analysis may contain errors or omissions. Important legal decisions should be
reviewed with a qualified legal professional.
