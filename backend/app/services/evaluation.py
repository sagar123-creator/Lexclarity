"""
Accuracy Evaluation Framework.

Runs the real system against a labelled dataset (JSONL) and computes actual
metrics — never hardcoded. Supported item types:

  qa      — question answering: retrieval precision/recall, answer token-F1,
            citation correctness, unsupported-claim detection stats
  risk    — risk-detection precision / recall / F1 over documented categories
  clause  — clause-category recall + quote fidelity

Dataset items look like:
  {"id": "qa-1", "type": "qa",
   "document": {"name": "...", "path": "sample_documents/...txt"},
   "question": "...", "reference_answers": ["..."],
   "reference_source_text": "..." , "category": "termination"}
  {"id": "risk-1", "type": "risk",
   "document": {...},
   "expected_categories": ["unlimited_liability", "one_sided_termination"]}

Documents are processed through the real pipeline (with the configured LLM),
so an evaluation run measures the system end-to-end.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services import pipeline
from app.services.embeddings import embed_query
from app.services.vector_store import get_vector_store
from app.services.verification import split_claims, SUPPORTED

_WORD_RE = re.compile(r"[a-z0-9$€£%.,]+")

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "to", "of", "and", "or", "in",
    "on", "for", "with", "that", "this", "it", "as", "at", "by", "an", "from", "what",
    "who", "when", "how", "does", "do", "did", "if", "their", "there", "any", "must",
    "shall", "may", "can", "not", "no", "you", "your", "we", "our", "they", "them",
}


def _tokens(text: str) -> list[str]:
    return [t for t in _WORD_RE.findall((text or "").lower()) if t not in STOPWORDS and len(t) > 1]


def token_f1(prediction: str, reference: str) -> float:
    pred_tokens = _tokens(prediction)
    ref_tokens = _tokens(reference)
    if not pred_tokens or not ref_tokens:
        return 0.0
    common: dict[str, int] = {}
    for t in pred_tokens:
        common[t] = common.get(t, 0)
    overlap = 0
    ref_counts: dict[str, int] = {}
    for t in ref_tokens:
        ref_counts[t] = ref_counts.get(t, 0) + 1
    pred_counts: dict[str, int] = {}
    for t in pred_tokens:
        pred_counts[t] = pred_counts.get(t, 0) + 1
    for t, c in pred_counts.items():
        overlap += min(c, ref_counts.get(t, 0))
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred_tokens)
    recall = overlap / len(ref_tokens)
    return 2 * precision * recall / (precision + recall)


def best_reference_f1(prediction: str, references: list[str]) -> float:
    if not references:
        return 0.0
    return max(token_f1(prediction, r) for r in references)


def _retrieval_for_document(document_id: str, question: str, top_k: int) -> list:
    store = get_vector_store()
    query_emb = embed_query(question)
    return store.query(document_id, query_emb, top_k=top_k)


def _retrieval_metrics(retrieved: list, reference_source_text: str) -> dict:
    ref_tokens = set(_tokens(reference_source_text))
    if not ref_tokens:
        return {"precision": None, "recall": None}
    hits = 0
    retrieved_tokens: set[str] = set()
    for r in retrieved:
        chunk_tokens = set(_tokens(r.text))
        retrieved_tokens |= chunk_tokens
        if chunk_tokens & ref_tokens:
            hits += 1
    precision = hits / len(retrieved) if retrieved else 0.0
    recall = len(ref_tokens & retrieved_tokens) / len(ref_tokens) if ref_tokens else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3)}


def _citation_correctness(citations: list[dict], reference_source_text: str) -> float | None:
    if not citations:
        return None
    ref_tokens = set(_tokens(reference_source_text))
    if not ref_tokens:
        return None
    correct = 0
    store = get_vector_store()  # noqa: F841 (kept for parity; chunks looked up via DB)
    for c in citations:
        text = c.get("snippet") or ""
        if set(_tokens(text)) & ref_tokens:
            correct += 1
    return round(correct / len(citations), 3)


def _ensure_eval_document(db: Session, doc_spec: dict, base_dir: str) -> models.Document | None:
    """Create (and process) a document for evaluation, reusing an existing
    ready document with the same filename when available."""
    name = doc_spec["name"]
    path = doc_spec.get("path")
    abs_path = path if os.path.isabs(path) else os.path.join(base_dir, path)

    user = db.query(models.User).filter(models.User.id == "eval-runner").first()
    if not user:
        user = models.User(id="eval-runner", email="eval-runner@lexclarity.local", name="Evaluation Runner")
        db.add(user)
        db.commit()

    existing = (
        db.query(models.Document)
        .filter(models.Document.user_id == user.id, models.Document.filename == name,
                models.Document.status == "ready")
        .first()
    )
    if existing:
        return existing

    if not os.path.exists(abs_path):
        return None

    from app.utils.file_validation import build_storage_path
    ext = os.path.splitext(name)[1].lower() or ".txt"
    document_id = str(uuid.uuid4())
    storage_path = build_storage_path(document_id, ext)
    with open(abs_path, "rb") as f:
        content = f.read()
    with open(storage_path, "wb") as f:
        f.write(content)

    document = models.Document(
        id=document_id,
        user_id=user.id,
        filename=name,
        file_type=ext.lstrip("."),
        file_size_bytes=len(content),
        storage_path=storage_path,
        status="uploaded",
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    pipeline.process_document(db, document)
    db.refresh(document)
    return document if document.status == "ready" else None


def _run_qa(db: Session, item: dict, base_dir: str) -> dict:
    document = _ensure_eval_document(db, item["document"], base_dir)
    if document is None:
        return {"id": item["id"], "type": "qa", "error": "document unavailable"}

    from app.services.chatbot import answer_question
    result = answer_question(document.id, item["question"], history=[])

    retrieved = _retrieval_for_document(document.id, item["question"], top_k=settings.RETRIEVAL_TOP_K)
    ret_metrics = _retrieval_metrics(retrieved, item.get("reference_source_text", ""))

    answer_f1 = best_reference_f1(result["answer"], item.get("reference_answers", []))
    found = result["confidence"] != "not_found"
    expected_found = item.get("expect_answer", True)

    claims = result.get("verification", {}).get("claims", [])
    supported_claims = sum(1 for c in claims if c.get("status") == SUPPORTED)

    return {
        "id": item["id"],
        "type": "qa",
        "category": item.get("category"),
        "document_type": document.document_type,
        "found": found,
        "expected_found": expected_found,
        "answer_f1": round(answer_f1, 3),
        "retrieval_precision": ret_metrics["precision"],
        "retrieval_recall": ret_metrics["recall"],
        "citation_correctness": _citation_correctness(result["citations"], item.get("reference_source_text", "")),
        "claims_total": len(claims),
        "claims_supported": supported_claims,
        "claims_flagged_unsupported": len(claims) - supported_claims,
    }


def _run_risk(db: Session, item: dict, base_dir: str) -> dict:
    document = _ensure_eval_document(db, item["document"], base_dir)
    if document is None:
        return {"id": item["id"], "type": "risk", "error": "document unavailable"}
    predicted = {(r.category or "other") for r in db.query(models.Risk).filter(models.Risk.document_id == document.id).all()}
    expected = set(item.get("expected_categories", []))
    tp = len(predicted & expected)
    fp = len(predicted - expected)
    fn = len(expected - predicted)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "id": item["id"],
        "type": "risk",
        "document_type": document.document_type,
        "expected": sorted(expected),
        "predicted": sorted(predicted),
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
    }


def _run_clause(db: Session, item: dict, base_dir: str) -> dict:
    document = _ensure_eval_document(db, item["document"], base_dir)
    if document is None:
        return {"id": item["id"], "type": "clause", "error": "document unavailable"}
    from app.services.evidence import find_quote

    clauses = db.query(models.Clause).filter(models.Clause.document_id == document.id).all()
    predicted = {(c.category or "").lower() for c in clauses}
    expected = {c.lower() for c in item.get("expected_categories", [])}
    recall = len(predicted & expected) / len(expected) if expected else 0.0

    # Quote fidelity: extracted original_text must exist in the document text.
    all_text = " ".join(p.text for p in db.query(models.DocumentPage).filter(models.DocumentPage.document_id == document.id).all())
    quote_hits = sum(1 for c in clauses if c.original_text and find_quote(c.original_text, all_text).found)
    quote_fidelity = quote_hits / len(clauses) if clauses else None

    return {
        "id": item["id"],
        "type": "clause",
        "document_type": document.document_type,
        "expected": sorted(expected),
        "predicted": sorted(predicted),
        "category_recall": round(recall, 3),
        "quote_fidelity": round(quote_fidelity, 3) if quote_fidelity is not None else None,
    }


def _extraction_quality(db: Session, document: models.Document) -> dict:
    pages = db.query(models.DocumentPage).filter(models.DocumentPage.document_id == document.id).all()
    total = len(pages)
    with_text = sum(1 for p in pages if len((p.text or "").strip()) >= 20)
    chars = sum(len(p.text or "") for p in pages)
    return {
        "document_id": document.id,
        "filename": document.filename,
        "document_type": document.document_type,
        "pages": total,
        "pages_with_text": with_text,
        "page_coverage": round(with_text / total, 3) if total else 0.0,
        "total_chars": chars,
        "ocr_used": bool(document.ocr_used),
        "extraction_method": document.extraction_method,
    }


def _aggregate(results: list[dict]) -> dict:
    def mean(values):
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 3) if values else None

    qa = [r for r in results if r["type"] == "qa" and "error" not in r]
    risk = [r for r in results if r["type"] == "risk" and "error" not in r]
    clause = [r for r in results if r["type"] == "clause" and "error" not in r]

    metrics: dict = {"items_evaluated": len(results), "items_failed": sum(1 for r in results if "error" in r)}

    if qa:
        tp = sum(1 for r in qa if r["found"] and r["expected_found"])
        fp = sum(1 for r in qa if r["found"] and not r["expected_found"])
        fn = sum(1 for r in qa if not r["found"] and r["expected_found"])
        metrics["qa"] = {
            "count": len(qa),
            "answer_f1": mean([r["answer_f1"] for r in qa]),
            "retrieval_precision": mean([r["retrieval_precision"] for r in qa]),
            "retrieval_recall": mean([r["retrieval_recall"] for r in qa]),
            "citation_correctness": mean([r["citation_correctness"] for r in qa]),
            "answer_presence_precision": round(tp / (tp + fp), 3) if (tp + fp) else None,
            "answer_presence_recall": round(tp / (tp + fn), 3) if (tp + fn) else None,
            "claims_total": sum(r["claims_total"] for r in qa),
            "claims_flagged_unsupported": sum(r["claims_flagged_unsupported"] for r in qa),
        }
        by_cat: dict[str, list] = defaultdict(list)
        for r in qa:
            by_cat[r.get("category") or "uncategorized"].append(r)
        metrics["qa_by_question_category"] = {
            cat: {"count": len(items), "answer_f1": mean([i["answer_f1"] for i in items])}
            for cat, items in by_cat.items()
        }
        by_doc_type: dict[str, list] = defaultdict(list)
        for r in qa:
            by_doc_type[r.get("document_type") or "unknown"].append(r)
        metrics["qa_by_document_type"] = {
            dt: {"count": len(items), "answer_f1": mean([i["answer_f1"] for i in items])}
            for dt, items in by_doc_type.items()
        }

    if risk:
        tp = sum(r["tp"] for r in risk)
        fp = sum(r["fp"] for r in risk)
        fn = sum(r["fn"] for r in risk)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        metrics["risk_detection"] = {
            "count": len(risk),
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        }

    if clause:
        metrics["clause_extraction"] = {
            "count": len(clause),
            "category_recall": mean([r["category_recall"] for r in clause]),
            "quote_fidelity": mean([r["quote_fidelity"] for r in clause]),
        }

    return metrics


def run_evaluation(db: Session, dataset_path: str | None = None) -> models.EvaluationRun:
    """Execute a full evaluation run over the labelled dataset."""
    path = dataset_path or settings.EVAL_DATASET_PATH
    base_dir = os.path.dirname(os.path.dirname(path))  # backend/ root

    run = models.EvaluationRun(dataset_name=os.path.basename(path), status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        with open(path, "r", encoding="utf-8") as f:
            items = [json.loads(line) for line in f if line.strip()]
    except Exception as e:  # noqa: BLE001
        run.status = "failed"
        run.error_message = f"Could not load dataset: {e}"
        run.finished_at = datetime.utcnow()
        db.commit()
        return run

    results: list[dict] = []
    extraction: list[dict] = []
    seen_docs: set[str] = set()

    for item in items:
        try:
            if item.get("type") == "qa":
                results.append(_run_qa(db, item, base_dir))
            elif item.get("type") == "risk":
                results.append(_run_risk(db, item, base_dir))
            elif item.get("type") == "clause":
                results.append(_run_clause(db, item, base_dir))
            else:
                results.append({"id": item.get("id"), "type": item.get("type"), "error": "unknown item type"})
        except Exception as e:  # noqa: BLE001 - a single bad item must not kill the run
            results.append({"id": item.get("id"), "type": item.get("type"), "error": str(e)[:300]})

        doc_spec = item.get("document") or {}
        name = doc_spec.get("name")
        if name and name not in seen_docs:
            seen_docs.add(name)
            doc = (
                db.query(models.Document)
                .join(models.User, models.Document.user_id == models.User.id)
                .filter(models.User.id == "eval-runner", models.Document.filename == name)
                .first()
            )
            if doc:
                extraction.append(_extraction_quality(db, doc))

    metrics = _aggregate(results)
    if extraction:
        metrics["extraction_quality"] = {
            "documents": len(extraction),
            "page_coverage": round(sum(e["page_coverage"] for e in extraction) / len(extraction), 3),
            "ocr_used_any": any(e["ocr_used"] for e in extraction),
        }

    run.status = "completed"
    run.metrics = metrics
    run.item_results = results + [{"type": "_extraction", "detail": extraction}]
    run.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(run)
    return run
