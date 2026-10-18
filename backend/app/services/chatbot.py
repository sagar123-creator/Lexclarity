"""
The RAG chatbot — LexClarity's core feature.

Flow per message:
  1. Embed the user's question.
  2. Semantic search against this document's chunks only (metadata-filtered
     by document_id — never leaks other documents' content).
  3. Keep chunks above RETRIEVAL_MIN_SIMILARITY, capped at RETRIEVAL_TOP_K.
  4. If nothing clears the similarity bar, skip the LLM call entirely and
     return the "not found in document" response — this is what prevents
     hallucination on off-topic questions.
  5. Otherwise, build a context block (with recent conversation history for
     follow-ups) and ask the LLM to answer ONLY from that context, citing
     page/section for every claim.
  6. Parse the structured response into an answer + citation list.
"""
from app.config import settings
from app.services.embeddings import embed_query
from app.services.vector_store import get_vector_store
from app.services.llm import complete_json, LLMError
from app.services.verification import Passage, verify_answer

SYSTEM_PROMPT = """You are LexClarity, an AI assistant that analyzes legal documents.

Answer questions ONLY using information retrieved from the uploaded document excerpts
provided to you in this prompt. Do not invent facts. Do not assume information that is
not present in the excerpts.

If the excerpts do not contain enough information to answer the question, say so clearly
rather than guessing.

When possible, cite the relevant page and section for every factual claim.

Explain legal language in simple terms when relevant.

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
"not_found" means the excerpts contain nothing relevant to the question.
"low_confidence" means the excerpts are only tangentially related.
"""


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(no previous messages)"
    lines = []
    for m in history[-6:]:
        speaker = "User" if m["role"] == "user" else "LexClarity"
        lines.append(f"{speaker}: {m['content']}")
    return "\n".join(lines)


def answer_question(document_id: str, question: str, history: list[dict], ocr_pages: set[int] | None = None) -> dict:
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
        return {
            "answer": "I couldn't find this information in the uploaded document.",
            "citations": [],
            "confidence": "not_found",
            "verification": {"overall": "insufficient", "claims": []},
        }

    context = "\n\n".join(
        f"[chunk_id={r.chunk_id} page={r.page_number} section={r.section_heading or 'n/a'} "
        f"similarity={r.similarity:.2f}]\n{r.text}"
        for r in relevant
    )

    prompt = f"""Conversation so far:
{_format_history(history)}

Relevant excerpts retrieved from the uploaded document:
{context}

Current question: {question}

Answer the current question using only the excerpts above and the conversation context.
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

    answer_text = result.get("answer", "").strip() or "I couldn't find this information in the uploaded document."

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
