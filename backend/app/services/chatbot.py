"""
The RAG chatbot — LexClarity's core feature.

Flow per message:
  1. Embed the user's question.
  2. Semantic search against this document's chunks only (metadata-filtered
     by document_id — never leaks other documents' content).
  3. Prefer chunks above RETRIEVAL_MIN_SIMILARITY, capped at RETRIEVAL_TOP_K.
     If the strict bar isn't cleared, fall back to the closest chunks above
     RETRIEVAL_MIN_SIMILARITY_FLOOR — local embedding models routinely score
     genuine matches below 0.25 (short documents are often a single chunk), so
     a hard cutoff there silently rejected valid questions.
  4. If nothing clears the floor either, skip the LLM call entirely and return
     the "not found in document" response — this is what prevents hallucination
     on off-topic questions.
  5. Otherwise, build a context block (with recent conversation history for
     follow-ups) and ask the LLM to answer ONLY from that context: a direct,
     plain-English answer first (not a paste of the document), citing page/
     section for every claim — and to return "not_found" when the excerpts
     don't answer, in which case it must invite the user to ask a question the
     document can actually answer.
  6. Parse the structured response into an answer + citation list.
"""
from app.config import settings
from app.services.embeddings import embed_query
from app.services.vector_store import get_vector_store
from app.services.llm import complete_json, LLMError
from app.services.verification import Passage, verify_answer

SYSTEM_PROMPT = """You are LexClarity, an AI assistant that answers questions about ONE uploaded legal document.

You are given excerpts retrieved from that document. Answer ONLY from those excerpts.

How to answer:
- Start with the direct answer to the question, in plain English. Then briefly explain or
  quote the wording that supports it (any direct quote under 25 words).
- Do not paste or paraphrase large blocks of the document without first answering the
  question — the user asked a question and wants it answered, not a copy of the text.
- Never invent facts, dates, names, amounts or obligations that are not in the excerpts.
- Explain legal language in simple terms.

When you cannot answer:
- If the excerpts do not contain the information needed, or the question is not about this
  document (general knowledge, small talk, unrelated topics), return confidence "not_found".
- In that case the answer must briefly say this document does not cover it, and invite the
  user to ask a question about this document (say what the document is about, based on the
  excerpts). Do not attempt the question and do not guess.

Confidence values:
- "answered": the excerpts clearly support the answer.
- "low_confidence": the excerpts are only tangentially related.
- "not_found": the excerpts contain nothing relevant to the question.

Legal-safety rules:
Do not present yourself as a lawyer. Do not provide definitive legal advice. When a
question calls for a legal judgment (e.g. "should I sign this"), clearly distinguish:
1. What the document says.
2. What the clause may mean in plain terms.
3. That professional legal advice may be appropriate for a decision like this.

Always respond with a JSON object of the form:
{
  "confidence": "answered" | "not_found" | "low_confidence",
  "answer": "your answer text",
  "citations": [{"page_number": int, "section": str, "chunk_id": str}]
}
Only cite chunk_ids that appear in the excerpts provided in the prompt.
"""

# Shown when retrieval can't reach the model (nothing above the floor) or the model
# returns an empty answer — phrased so the user knows what to ask next.
NOT_FOUND_ANSWER = (
    "I couldn't find anything about that in this document, so I won't guess. "
    "I can only answer questions about the uploaded file — try asking about its "
    "parties, key dates, obligations, risks or termination terms."
)


def _not_found(answer: str = NOT_FOUND_ANSWER) -> dict:
    return {
        "answer": answer,
        "citations": [],
        "confidence": "not_found",
        "verification": {"overall": "insufficient", "claims": []},
    }


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(no previous messages)"
    lines = []
    for m in history[-6:]:
        speaker = "User" if m["role"] == "user" else "LexClarity"
        lines.append(f"{speaker}: {m['content']}")
    return "\n".join(lines)


def answer_question(
    document_id: str,
    question: str,
    history: list[dict],
    ocr_pages: set[int] | None = None,
    document_name: str | None = None,
) -> dict:
    """Returns {answer, citations, confidence, verification}.

    After generation, every factual claim in the answer is verified against
    the retrieved passages by the Trust & Verification engine; the result is
    returned alongside the answer so unsupported claims are visible.
    """
    ocr_pages = ocr_pages or set()
    query_emb = embed_query(question)
    store = get_vector_store()
    retrieved = store.query(document_id, query_emb, top_k=settings.RETRIEVAL_TOP_K)

    relevant = [r for r in retrieved if r.similarity >= settings.RETRIEVAL_MIN_SIMILARITY]

    if not relevant:
        # Near-miss fallback: local embedding models often score genuine matches
        # (short questions, single-chunk documents) below the strict bar, so a
        # hard cutoff there rejected valid questions. Hand the closest passages
        # to the model instead — it must return "not_found" when they don't
        # actually answer, which is the real hallucination guard.
        relevant = [
            r for r in retrieved[:3]
            if r.similarity >= settings.RETRIEVAL_MIN_SIMILARITY_FLOOR
        ]

    if not relevant:
        return _not_found()

    context = "\n\n".join(
        f"[chunk_id={r.chunk_id} page={r.page_number} section={r.section_heading or 'n/a'} "
        f"similarity={r.similarity:.2f}]\n{r.text}"
        for r in relevant
    )

    prompt = f"""Conversation so far:
{_format_history(history)}

Document: {document_name or "the uploaded document"}

Relevant excerpts retrieved from the document:
{context}

Current question: {question}

Answer the current question using only the excerpts above and the conversation context.
Lead with the direct answer in plain English. If the excerpts do not answer the question,
or the question is not about this document, respond with confidence "not_found", say the
document does not cover it, and invite the user to ask a question about this document.
Respond with the JSON object format specified in your instructions."""

    try:
        result = complete_json(SYSTEM_PROMPT, prompt, max_tokens=1200)
    except LLMError as e:
        return {
            "answer": f"I ran into a problem generating an answer: {e}",
            "citations": [],
            "confidence": "low_confidence",
            "verification": {"overall": "insufficient", "claims": []},
        }

    if not isinstance(result, dict):
        return {
            "answer": "I couldn't generate a reliable answer from the document. Please try rephrasing your question.",
            "citations": [],
            "confidence": "low_confidence",
            "verification": {"overall": "insufficient", "claims": []},
        }

    citations = result.get("citations") or []
    # attach snippet text for UI display, matched back to retrieved chunks;
    # citations pointing at chunks that were NOT retrieved are flagged so a
    # model can never invent a source reference.
    by_id = {r.chunk_id: r for r in relevant}
    enriched = []
    for c in citations:
        chunk = by_id.get(c.get("chunk_id"))
        enriched.append({
            "chunk_id": c.get("chunk_id") if chunk else None,
            "page_number": (c.get("page_number") or chunk.page_number) if chunk else None,
            "section_reference": (c.get("section") or (chunk.section_heading if chunk else None)),
            "snippet": (chunk.text[:220] + "…") if chunk and len(chunk.text) > 220 else (chunk.text if chunk else None),
            "verified": chunk is not None,
        })
        if chunk is None:
            enriched[-1]["warning"] = "This reference could not be matched to a retrieved passage and is not shown as a source."

    answer_text = result.get("answer", "").strip() or NOT_FOUND_ANSWER

    # --- Claim verification against retrieved evidence ---
    passages = [
        Passage(
            text=r.text,
            similarity=r.similarity,
            chunk_id=r.chunk_id,
            page_number=r.page_number,
            section_heading=r.section_heading,
            ocr_used=r.page_number in ocr_pages,
        )
        for r in relevant
    ]
    verification = verify_answer(answer_text, passages)

    # A contradicted answer must not be presented as a reliable answer.
    confidence = result.get("confidence", "answered")
    if verification["overall"] == "contradicted" and confidence == "answered":
        confidence = "low_confidence"

    return {
        "answer": answer_text,
        "citations": enriched,
        "confidence": confidence,
        "verification": verification,
    }
