from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.api.auth import get_current_user
from app.api.upload import _get_owned_document
from app.services.chatbot import answer_question

router = APIRouter(prefix="/api/documents", tags=["chat"])


@router.post("/{document_id}/chat", response_model=schemas.ChatResponse)
def chat(document_id: str, body: schemas.ChatRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    if doc.status != "ready":
        raise HTTPException(status_code=409, detail=f"Document is still processing (status: {doc.status}). Please wait before chatting.")

    if body.conversation_id:
        conversation = (
            db.query(models.Conversation)
            .filter(models.Conversation.id == body.conversation_id, models.Conversation.document_id == doc.id)
            .first()
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found.")
    else:
        conversation = models.Conversation(document_id=doc.id)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    history = [{"role": m.role, "content": m.content} for m in conversation.messages]

    user_message = models.Message(conversation_id=conversation.id, role="user", content=body.message)
    db.add(user_message)
    db.commit()

    ocr_pages = {
        p.page_number
        for p in db.query(models.DocumentPage).filter(
            models.DocumentPage.document_id == doc.id,
            models.DocumentPage.ocr_used == True,  # noqa: E712
        ).all()
    }
    result = answer_question(doc.id, body.message, history, ocr_pages=ocr_pages)

    assistant_message = models.Message(
        conversation_id=conversation.id,
        role="assistant",
        content=result["answer"],
        citations=result["citations"],
        confidence=result["confidence"],
    )
    db.add(assistant_message)

    # Persist claim verifications for auditability.
    for claim in (result.get("verification") or {}).get("claims", []):
        db.add(models.Verification(
            document_id=doc.id,
            subject_type="answer",
            subject_id=assistant_message.id,
            claim_text=claim.get("claim", ""),
            status=claim.get("status", "insufficient"),
            method=claim.get("method", "unavailable"),
            score=claim.get("score"),
            explanation=claim.get("explanation", ""),
            evidence_chunk_ids=[claim["evidence_chunk_id"]] if claim.get("evidence_chunk_id") else [],
            evidence_summary=claim.get("evidence_excerpt"),
        ))
    db.commit()

    return schemas.ChatResponse(
        conversation_id=conversation.id,
        answer=result["answer"],
        citations=[schemas.CitationOut(**c) for c in result["citations"]],
        confidence=result["confidence"],
        verification=result.get("verification"),
    )


@router.get("/{document_id}/conversations/{conversation_id}", response_model=schemas.ConversationOut)
def get_conversation(document_id: str, conversation_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = _get_owned_document(db, document_id, user)
    conversation = (
        db.query(models.Conversation)
        .filter(models.Conversation.id == conversation_id, models.Conversation.document_id == doc.id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation
