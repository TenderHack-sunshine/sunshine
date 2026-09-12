from __future__ import annotations

from .prompts import EVIDENCE_GENERATION_POLICY, OPERATOR_FALLBACK


class EvidenceGenerator:
    """Extractive answer mode. It deliberately cannot fabricate an answer."""

    evidence_policy = EVIDENCE_GENERATION_POLICY

    def __init__(self, minimum_score: float = 0.005):
        self.minimum_score = minimum_score

    def answer(self, evidence: list[dict]) -> dict:
        best = evidence[0] if evidence else None
        score = next((best[key] for key in ("reranker_score", "rrf_score", "score", "raw_score") if best and best.get(key) is not None), 0.0)
        if best is None or float(score) < self.minimum_score:
            return {"answer": OPERATOR_FALLBACK, "used_evidence": False, "evidence": []}
        prefix = ""
        if best.get("authority") == "case_history":
            prefix = "Похожее историческое обращение (проверьте применимость решения):\n"
        return {
            "answer": prefix + best["text"], "used_evidence": True,
            "evidence": [{key: best.get(key) for key in (
                "source", "source_path", "title", "page", "page_start", "section", "score", "authority", "source_type", "retrieval_method", "chunk_id",
            )}],
        }
