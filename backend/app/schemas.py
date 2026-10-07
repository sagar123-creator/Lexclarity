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


class ClauseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    category: str
    title: str
    original_text: Optional[str] = None
    plain_explanation: Optional[str] = None
    page_number: Optional[int] = None
    section_reference: Optional[str] = None


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


class ObligationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    party_name: str
    obligation_text: str
    page_number: Optional[int] = None
    section_reference: Optional[str] = None


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
