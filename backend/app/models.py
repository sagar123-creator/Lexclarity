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
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, Integer, Float, Boolean, JSON
)
from sqlalchemy.orm import relationship

from app.database import Base


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

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
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
