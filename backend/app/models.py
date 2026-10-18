"""
Database schema.

users                -> account owning documents
documents            -> uploaded files + processing status
document_chunks      -> RAG chunks (text stored here; embeddings live in the
                        vector store, cross-referenced by chunk id)
document_analysis    -> one-row structured analysis result per document
clauses              -> extracted key clauses
risks                -> extracted risk items
obligations          -> extracted per-party obligations
entities             -> extracted parties/entities
important_dates      -> extracted dates/deadlines
conversations        -> a chat thread scoped to one document
messages             -> individual chat turns (user/assistant) + citations

Added by the trust/action-platform upgrade:

document_pages       -> full page text (source of truth for the evidence viewer)
verifications        -> per-claim verification results (supported / contradicted / ...)
workspaces           -> multi-document case workspaces
workspace_documents  -> workspace <-> document membership
action_items         -> Legal Action Center items (from findings)
drafts               -> user-editable generated documents (emails, letters, ...)
clause_suggestions   -> AI negotiation suggestions for a selected clause
reminders            -> user-consented deadline reminders
checklist_items      -> missing-clause detector results
comparisons          -> persisted contract comparison results
evaluation_runs      -> accuracy-evaluation runs with real computed metrics
audit_log            -> records of consequential user-approved actions
"""
import re
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, Integer, Float, Boolean, JSON
)
from sqlalchemy.orm import relationship, validates

from app.database import Base

# Canonical [PLACEHOLDER: ...] pattern for generated drafts. Lives here (not in
# services/generator) so the model can keep `placeholders` consistent with
# `content` on every write; services import it from here.
PLACEHOLDER_RE = re.compile(r"\[PLACEHOLDER:[^\]]*\]")


def gen_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_id)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship("Document", back_populates="owner", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # pdf | docx | txt
    file_size_bytes = Column(Integer, nullable=False)
    storage_path = Column(String, nullable=False)

    status = Column(String, default="uploaded", index=True)
    # uploaded -> extracting -> chunking -> embedding -> analyzing -> ready | failed
    error_message = Column(Text, nullable=True)

    page_count = Column(Integer, nullable=True)
    document_type = Column(String, nullable=True)  # e.g. "Employment Agreement"
    overall_risk_level = Column(String, nullable=True)  # High | Medium | Low
    # How text was obtained: text | ocr | mixed | unknown (set by the parser)
    extraction_method = Column(String, nullable=True)
    # True when OCR was used for at least one page — surfaced in the UI so
    # quotes from OCR'd text can be inspected against the original page.
    ocr_used = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    pages = relationship("DocumentPage", back_populates="document", cascade="all, delete-orphan")
    analysis = relationship("DocumentAnalysis", back_populates="document", uselist=False, cascade="all, delete-orphan")
    clauses = relationship("Clause", back_populates="document", cascade="all, delete-orphan")
    risks = relationship("Risk", back_populates="document", cascade="all, delete-orphan")
    obligations = relationship("Obligation", back_populates="document", cascade="all, delete-orphan")
    entities = relationship("Entity", back_populates="document", cascade="all, delete-orphan")
    important_dates = relationship("ImportantDate", back_populates="document", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(String, primary_key=True, default=gen_id)  # also used as vector-store id
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)

    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)
    section_heading = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=True)
    embedded = Column(Boolean, default=False)

    document = relationship("Document", back_populates="chunks")


class DocumentPage(Base):
    """Persisted full text of each page — the source of truth for the
    evidence viewer, so users can inspect the exact text a citation came
    from (including OCR-derived text, flagged via `ocr_used`)."""

    __tablename__ = "document_pages"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)

    page_number = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    ocr_used = Column(Boolean, nullable=False, default=False)

    document = relationship("Document", back_populates="pages")


class DocumentAnalysis(Base):
    __tablename__ = "document_analysis"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, unique=True, index=True)

    executive_summary = Column(Text, nullable=True)
    document_type = Column(String, nullable=True)
    plain_english_overview = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="analysis")


class Clause(Base):
    __tablename__ = "clauses"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)

    category = Column(String, nullable=False)  # Termination, Payment, Confidentiality...
    title = Column(String, nullable=False)
    original_text = Column(Text, nullable=True)
    plain_explanation = Column(Text, nullable=True)
    page_number = Column(Integer, nullable=True)
    section_reference = Column(String, nullable=True)
    source_chunk_id = Column(String, nullable=True)

    # --- Enrichment (added by the clause-analysis upgrade; all optional) ---
    parties = Column(JSON, nullable=True)          # list[str] of parties referenced
    rights_obligations = Column(Text, nullable=True)  # plain-English rights/obligations
    concerns = Column(Text, nullable=True)         # potential concerns (hedged)
    verification_status = Column(String, nullable=True)  # supported|contradicted|insufficient|needs_review|unverified
    evidence_quote = Column(Text, nullable=True)   # exact quotation validated against source chunk
    char_start = Column(Integer, nullable=True)    # offset within source chunk/page, when found
    char_end = Column(Integer, nullable=True)

    document = relationship("Document", back_populates="clauses")


class Risk(Base):
    __tablename__ = "risks"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)

    level = Column(String, nullable=False)  # High | Medium | Low
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    why_it_matters = Column(Text, nullable=False)
    plain_explanation = Column(Text, nullable=True)
    page_number = Column(Integer, nullable=True)
    section_reference = Column(String, nullable=True)
    source_chunk_id = Column(String, nullable=True)

    # --- Structured risk data (added by the risk-detection upgrade) ---
    category = Column(String, nullable=True)          # see services/risk_rules.RISK_CATEGORIES
    affected_party = Column(String, nullable=True)    # party the risk likely affects
    evidence_quote = Column(Text, nullable=True)      # quotation validated against the source chunk
    suggested_action = Column(Text, nullable=True)    # recommended next step
    severity_rationale = Column(Text, nullable=True)  # why this severity (rubric rules that fired)
    verification_status = Column(String, nullable=True)  # supported|contradicted|insufficient|needs_review
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)

    document = relationship("Document", back_populates="risks")


class Obligation(Base):
    __tablename__ = "obligations"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)

    party_name = Column(String, nullable=False)
    obligation_text = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=True)
    section_reference = Column(String, nullable=True)
    source_chunk_id = Column(String, nullable=True)

    # --- Enrichment ---
    deadline_text = Column(String, nullable=True)    # e.g. "within 30 days"
    trigger_event = Column(String, nullable=True)    # e.g. "upon written notice"
    conditions = Column(Text, nullable=True)         # conditions/exceptions
    verification_status = Column(String, nullable=True)
    evidence_quote = Column(Text, nullable=True)
    task_status = Column(String, nullable=False, default="pending")  # pending|in_progress|completed

    document = relationship("Document", back_populates="obligations")


class Entity(Base):
    __tablename__ = "entities"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)

    name = Column(String, nullable=False)
    role = Column(String, nullable=True)  # e.g. "Employer", "Employee", "Landlord"
    entity_type = Column(String, nullable=True)  # organization | individual

    document = relationship("Document", back_populates="entities")


class ImportantDate(Base):
    __tablename__ = "important_dates"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)

    label = Column(String, nullable=False)  # "Start Date", "Notice Period", ...
    date_value = Column(String, nullable=True)  # kept as string: source docs are often imprecise
    description = Column(Text, nullable=True)
    page_number = Column(Integer, nullable=True)
    source_chunk_id = Column(String, nullable=True)

    # --- Enrichment ---
    normalized_date = Column(String, nullable=True)   # ISO date when reliably determinable
    date_kind = Column(String, nullable=True)         # explicit | inferred
    extraction_status = Column(String, nullable=True) # normalized | raw_only | uncertain
    evidence_quote = Column(Text, nullable=True)
    verification_status = Column(String, nullable=True)

    document = relationship("Document", back_populates="important_dates")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=gen_id)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)

    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    citations = Column(JSON, nullable=True)  # list[{page, section, chunk_id, snippet}]
    confidence = Column(String, nullable=True)  # answered | not_found | low_confidence
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class Verification(Base):
    """Result of verifying a single generated claim against source passages.

    Statuses: supported | contradicted | insufficient | needs_review
    Methods:  deterministic (value checks) | nli (NLI model) | llm (LLM judge,
              explicitly NOT treated as proof) | combined | unavailable
    """

    __tablename__ = "verifications"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)

    subject_type = Column(String, nullable=False)   # answer | risk | clause | claim | obligation | date
    subject_id = Column(String, nullable=True)      # row id of the subject, when applicable
    claim_text = Column(Text, nullable=False)

    status = Column(String, nullable=False)         # supported|contradicted|insufficient|needs_review
    method = Column(String, nullable=False)         # deterministic|nli|llm|combined|unavailable
    score = Column(Float, nullable=True)            # method-specific score (e.g. NLI prob); never presented as proof
    explanation = Column(Text, nullable=True)
    evidence_chunk_ids = Column(JSON, nullable=True)  # list[str]
    evidence_summary = Column(Text, nullable=True)    # best-matching passage excerpt
    created_at = Column(DateTime, default=datetime.utcnow)


class Workspace(Base):
    """A case workspace grouping related documents for cross-document work."""

    __tablename__ = "workspaces"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship("WorkspaceDocument", back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceDocument(Base):
    __tablename__ = "workspace_documents"

    id = Column(String, primary_key=True, default=gen_id)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False, index=True)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    added_at = Column(DateTime, default=datetime.utcnow)

    workspace = relationship("Workspace", back_populates="documents")
    document = relationship("Document")


class ActionItem(Base):
    """A Legal Action Center item: Risk -> Evidence -> Action.

    Actions are drafts/recommendations only — they require explicit user
    approval before any external communication, and LexClarity never sends
    anything automatically.
    """

    __tablename__ = "action_items"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)

    source_type = Column(String, nullable=False)    # risk | date | obligation | checklist
    source_id = Column(String, nullable=True)       # id of the originating finding
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    evidence = Column(JSON, nullable=True)          # [{chunk_id, page_number, quote}]
    suggested_action = Column(Text, nullable=True)
    priority = Column(String, nullable=False, default="medium")   # high|medium|low
    priority_reason = Column(Text, nullable=True)
    required_input = Column(Text, nullable=True)    # info the user must supply, if any
    status = Column(String, nullable=False, default="pending")    # pending|in_progress|completed
    decision = Column(String, nullable=False, default="undecided")  # undecided|accepted|rejected|deferred
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Draft(Base):
    """A user-editable generated document (email, letter, summary, ...)."""

    __tablename__ = "drafts"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    action_item_id = Column(String, nullable=True)  # ActionItem.id, when generated from an action

    kind = Column(String, nullable=False)  # negotiation_email|clarification_request|renewal_email|
                                           # clause_revision_request|formal_correspondence|
                                           # counter_proposal|lawyer_summary
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    placeholders = Column(JSON, nullable=True)   # list[str] of unfilled placeholders
    source_refs = Column(JSON, nullable=True)    # [{label, document_id, page_number, quote}]
    is_ai_generated = Column(Boolean, nullable=False, default=True)
    edited_by_user = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @validates("content")
    def _sync_placeholders(self, key, value):
        """Keep `placeholders` derived from the body text on every write.

        Any code path that changes the content (API update, service, direct
        model use) gets a correct, non-stale placeholder count — the count is
        a property of the text, not independent state to forget to update.
        """
        self.placeholders = sorted(set(PLACEHOLDER_RE.findall(value or "")))
        return value


class ClauseSuggestion(Base):
    """AI-generated negotiation suggestion for one clause. Explicitly labeled
    as a suggestion — never presented as legally valid or enforceable."""

    __tablename__ = "clause_suggestions"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    clause_id = Column(String, nullable=False, index=True)

    original_text = Column(Text, nullable=True)
    plain_explanation = Column(Text, nullable=True)
    concern = Column(Text, nullable=True)
    proposed_text = Column(Text, nullable=True)
    rationale = Column(Text, nullable=True)
    negotiation_points = Column(JSON, nullable=True)  # list[str]
    diff = Column(JSON, nullable=True)                 # {original, proposed} for side-by-side diff
    created_at = Column(DateTime, default=datetime.utcnow)


class Reminder(Base):
    """User-created deadline reminders. Never created automatically — the
    user must explicitly create one. No external notifications are sent;
    reminders are an in-app workflow only (see README)."""

    __tablename__ = "reminders"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    date_id = Column(String, nullable=True)  # ImportantDate.id, when linked

    title = Column(String, nullable=False)
    due_date = Column(String, nullable=True)      # ISO date when determinable, else raw text
    due_date_kind = Column(String, nullable=True) # explicit | inferred
    note = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="pending")  # pending|completed|dismissed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChecklistItem(Base):
    """Missing-clause detector result — a preliminary document review."""

    __tablename__ = "checklist_items"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)

    checklist_type = Column(String, nullable=False)  # e.g. "NDA"
    item_key = Column(String, nullable=False)
    item_label = Column(String, nullable=False)
    state = Column(String, nullable=False)  # detected|not_detected|unclear|not_applicable
    explanation = Column(Text, nullable=True)
    evidence_quote = Column(Text, nullable=True)
    page_number = Column(Integer, nullable=True)
    source_chunk_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Comparison(Base):
    """Persisted result of comparing two documents."""

    __tablename__ = "comparisons"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    document_a_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    document_b_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)

    status = Column(String, nullable=False, default="ready")  # ready | failed
    summary = Column(JSON, nullable=True)  # structured comparison result
    created_at = Column(DateTime, default=datetime.utcnow)


class EvaluationRun(Base):
    """One execution of the accuracy-evaluation framework over a labelled
    dataset. Metrics are computed from the actual run, never hardcoded."""

    __tablename__ = "evaluation_runs"

    id = Column(String, primary_key=True, default=gen_id)
    dataset_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="running")  # running|completed|failed
    error_message = Column(Text, nullable=True)
    metrics = Column(JSON, nullable=True)      # aggregate metrics
    item_results = Column(JSON, nullable=True) # per-item detail
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    """Audit trail for consequential, user-approved actions (e.g. accepting
    an action item, saving an edited draft that is marked approved to send)."""

    __tablename__ = "audit_log"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, nullable=True, index=True)
    document_id = Column(String, nullable=True, index=True)
    action = Column(String, nullable=False)   # e.g. "action_item.decision", "draft.approved_to_send"
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
