"""Deterministic RAG-side signal for unavailable or insufficient knowledge."""
from __future__ import annotations


def _score(items: list[dict]) -> float:
    if not items:
        return 0.0
    first = items[0]
    return float(first.get("raw_score", first.get("score", 0.0)) or 0.0)


def knowledge_gap(*, query: str, normalized_query: str, status: str, reason: str | None,
                  trace: dict | None = None, features: dict | None = None, candidates: list[dict] | None = None) -> dict:
    """Return an explainable, serializable signal without altering RAG decisions.

    ``ESCALATE_TO_OPERATOR`` means corpus evidence was insufficient. Clarification
    is represented separately as an ambiguous intent, not as a missing corpus.
    """
    trace, features, candidates = trace or {}, features or {}, candidates or []
    if status == "NEEDS_CLARIFICATION":
        return {
            "detected": False, "classification": "AMBIGUOUS_QUERY", "query": query,
            "normalized_query": normalized_query, "reason": "The query needs clarification before safe retrieval.",
        }
    if status != "ESCALATE_TO_OPERATOR":
        return {"detected": False, "classification": None}

    official = [item for item in candidates if item.get("authority") == "official"]
    if not candidates or not official:
        classification = "NO_RELEVANT_DOCUMENTS"
        explanation = "No sufficiently relevant official evidence was retrieved from the knowledge base."
    else:
        classification = "PARTIAL_KNOWLEDGE"
        explanation = "Relevant-looking documents were retrieved, but none met the evidence threshold for a safe answer."
    nearest = [
        {
            "chunk_id": item.get("chunk_id"), "document_id": item.get("document_id"),
            "document": item.get("source_path") or item.get("title") or item.get("document_id"),
            "source_type": item.get("source_type"), "authority": item.get("authority"),
            "score": float(item.get("raw_score", item.get("score", 0.0)) or 0.0),
        }
        for item in candidates[:3]
    ]
    return {
        "detected": True, "classification": classification, "query": query,
        "normalized_query": normalized_query,
        "retrieval": {
            "top_score": float(features.get("top_score", 0.0) or 0.0),
            "bm25_top_score": _score(trace.get("official_bm25", [])),
            "dense_top_score": _score(trace.get("official_dense", [])),
            "retriever_agreement": float(features.get("retrieval_agreement", 0.0) or 0.0),
            "official_candidates": int(features.get("num_official_candidates", 0) or 0),
        },
        "nearest_sources": nearest,
        "reason": explanation,
        "decision_reason": reason or "insufficient_evidence",
    }
