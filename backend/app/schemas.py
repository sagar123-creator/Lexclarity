from datetime import datetime
from typing import Optional, List, Any

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    error_message: Optional[str] = None
    page_count: Optional[int] = None
    document_type: Optional[str] = None
    overall_risk_level: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    document: DocumentOut
    message: str


class CitationOut(BaseModel):
    chunk_id: Optional[str] = None
    page_number: Optional[int] = None
    section_reference: Optional[str] = None
    snippet: Optional[str] = None
    # Citation integrity: whether this reference matched a real retrieved/source passage
    verified: Optional[bool] = None
    warning: Optional[str] = None
    # Present on evidence citations:
    document_id: Optional[str] = None
    quote: Optional[str] = None
    quote_verified: Optional[bool] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None


class ClauseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    category: str
    title: str
    original_text: Optional[str] = None
    plain_explanation: Optional[str] = None
    page_number: Optional[int] = None
    section_reference: Optional[str] = None
    # Enrichment
    parties: Optional[Any] = None
    rights_obligations: Optional[str] = None
    concerns: Optional[str] = None
    verification_status: Optional[str] = None
    evidence_quote: Optional[str] = None
    source_chunk_id: Optional[str] = None


class RiskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    level: str
    title: str
    description: str
    why_it_matters: str
    plain_explanation: Optional[str] = None
    page_number: Optional[int] = None
    section_reference: Optional[str] = None
    # Structured risk data
    category: Optional[str] = None
    affected_party: Optional[str] = None
    evidence_quote: Optional[str] = None
    suggested_action: Optional[str] = None
    severity_rationale: Optional[str] = None
    verification_status: Optional[str] = None
    source_chunk_id: Optional[str] = None


class ObligationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    party_name: str
    obligation_text: str
    page_number: Optional[int] = None
    section_reference: Optional[str] = None
    deadline_text: Optional[str] = None
    trigger_event: Optional[str] = None
    conditions: Optional[str] = None
    verification_status: Optional[str] = None
    evidence_quote: Optional[str] = None
    task_status: str = "pending"
    source_chunk_id: Optional[str] = None


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    role: Optional[str] = None
    entity_type: Optional[str] = None


class ImportantDateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    label: str
    date_value: Optional[str] = None
    description: Optional[str] = None
    page_number: Optional[int] = None
    normalized_date: Optional[str] = None
    date_kind: Optional[str] = None      # explicit | inferred
    extraction_status: Optional[str] = None  # normalized | raw_only | uncertain
    evidence_quote: Optional[str] = None
    verification_status: Optional[str] = None


class SummaryOut(BaseModel):
    executive_summary: Optional[str] = None
    document_type: Optional[str] = None
    plain_english_overview: Optional[str] = None
    entities: List[EntityOut] = []
    obligations: List[ObligationOut] = []
    important_dates: List[ImportantDateOut] = []


class AnalysisStatusOut(BaseModel):
    document_id: str
    status: str
    error_message: Optional[str] = None


class ChatRequest(BaseModel):
    document_id: str
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    citations: List[CitationOut] = []
    confidence: str  # answered | not_found | low_confidence
    verification: Optional[Any] = None  # {overall, claims: [...]}


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    role: str
    content: str
    citations: Optional[Any] = None
    confidence: Optional[str] = None
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    messages: List[MessageOut] = []


# ---------------------------------------------------------------------------
# Evidence viewer
# ---------------------------------------------------------------------------

class DocumentPageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    page_number: int
    text: str
    ocr_used: bool = False


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    chunk_index: int
    page_number: Optional[int] = None
    section_heading: Optional[str] = None
    text: str


# ---------------------------------------------------------------------------
# Trust & verification
# ---------------------------------------------------------------------------

class ClaimVerificationOut(BaseModel):
    claim: str
    status: str          # supported | contradicted | insufficient | needs_review
    method: str          # deterministic | nli | llm | combined | unavailable
    explanation: str
    score: Optional[float] = None
    evidence_chunk_id: Optional[str] = None
    evidence_page: Optional[int] = None
    evidence_excerpt: Optional[str] = None
    notes: List[str] = []


class VerifyClaimRequest(BaseModel):
    claim: str
    chunk_id: Optional[str] = None


class VerifyClaimResponse(BaseModel):
    document_id: str
    result: ClaimVerificationOut


# ---------------------------------------------------------------------------
# Legal Action Center
# ---------------------------------------------------------------------------

class ActionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    source_type: str
    source_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    evidence: Optional[Any] = None
    suggested_action: Optional[str] = None
    priority: str
    priority_reason: Optional[str] = None
    required_input: Optional[str] = None
    status: str
    decision: str
    created_at: datetime
    updated_at: datetime


class ActionItemUpdate(BaseModel):
    status: Optional[str] = None       # pending | in_progress | completed
    decision: Optional[str] = None     # undecided | accepted | rejected | deferred
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Document generator
# ---------------------------------------------------------------------------

class DraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    action_item_id: Optional[str] = None
    kind: str
    title: str
    content: str
    placeholders: Optional[Any] = None
    source_refs: Optional[Any] = None
    is_ai_generated: bool = True
    edited_by_user: bool = False
    created_at: datetime
    updated_at: datetime


class GenerateDraftRequest(BaseModel):
    kind: str
    source_ids: Optional[List[str]] = None
    action_item_id: Optional[str] = None
    user_instructions: Optional[str] = None


class DraftUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


# ---------------------------------------------------------------------------
# Negotiation assistant
# ---------------------------------------------------------------------------

class ClauseSuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    clause_id: str
    original_text: Optional[str] = None
    plain_explanation: Optional[str] = None
    concern: Optional[str] = None
    proposed_text: Optional[str] = None
    rationale: Optional[str] = None
    negotiation_points: Optional[Any] = None
    diff: Optional[Any] = None
    created_at: datetime


class NegotiateRequest(BaseModel):
    clause_id: str


# ---------------------------------------------------------------------------
# Deadline tracker
# ---------------------------------------------------------------------------

class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    date_id: Optional[str] = None
    title: str
    due_date: Optional[str] = None
    due_date_kind: Optional[str] = None  # explicit | inferred
    note: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime


class ReminderCreate(BaseModel):
    date_id: Optional[str] = None
    title: Optional[str] = None
    due_date: Optional[str] = None
    note: Optional[str] = None


class ReminderUpdate(BaseModel):
    title: Optional[str] = None
    due_date: Optional[str] = None
    note: Optional[str] = None
    status: Optional[str] = None  # pending | completed | dismissed


class ObligationUpdate(BaseModel):
    task_status: Optional[str] = None  # pending | in_progress | completed


# ---------------------------------------------------------------------------
# Missing-clause checklist
# ---------------------------------------------------------------------------

class ChecklistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    checklist_type: str
    item_key: str
    item_label: str
    state: str  # detected | not_detected | unclear | not_applicable
    explanation: Optional[str] = None
    evidence_quote: Optional[str] = None
    page_number: Optional[int] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Contract comparison
# ---------------------------------------------------------------------------

class CompareRequest(BaseModel):
    document_a_id: str
    document_b_id: str


class ComparisonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_a_id: str
    document_b_id: str
    status: str
    summary: Optional[Any] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Legal action plan
# ---------------------------------------------------------------------------

class PlanItemOut(BaseModel):
    action_id: str
    title: str
    priority: str
    priority_reason: Optional[str] = None
    related_finding_type: str
    suggested_action: Optional[str] = None
    required_input: Optional[str] = None
    status: str
    decision: str
    evidence: Optional[Any] = None


class ActionPlanOut(BaseModel):
    document_id: str
    generated_at: datetime
    items: List[PlanItemOut] = []
    disclaimer: str
