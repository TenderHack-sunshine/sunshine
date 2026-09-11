from __future__ import annotations

from .prompts import OPERATOR_FALLBACK


class EvidenceGenerator:
    """Extractive answer mode. It deliberately cannot fabricate an answer."""

    def __init__(self, minimum_score: float = 0.02):
        self.minimum_score = minimum_score

    def answer(self, evidence: list[dict]) -> dict:
        best = evidence[0] if evidence else None
        if best is None or best.get("score", 0.0) < self.minimum_score:
            return {"answer": OPERATOR_FALLBACK, "used_evidence": False, "evidence": []}
        return {
            "answer": best["text"], "used_evidence": True,
            "evidence": [{key: best.get(key) for key in ("source", "page", "section", "score", "authority", "chunk_id")}],
        }
