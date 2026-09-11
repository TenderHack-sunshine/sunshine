from __future__ import annotations

from src.retrieval.bm25 import tokenize


class TaxonomyRouter:
    """Replaceable baseline based only on the official taxonomy wording."""

    def __init__(self, taxonomy: list[dict[str, str | None]]):
        self.taxonomy = taxonomy

    def classify(self, query: str) -> dict[str, str | float | None]:
        query_terms = set(tokenize(query))
        if not query_terms or not self.taxonomy:
            return {"topic": None, "subtopic": None, "confidence": 0.0}
        best, best_score = None, 0.0
        for item in self.taxonomy:
            labels = " ".join(value for value in (item.get("topic"), item.get("subtopic")) if value)
            label_terms = set(tokenize(labels))
            if not label_terms:
                continue
            score = len(query_terms & label_terms) / len(query_terms | label_terms)
            if score > best_score:
                best, best_score = item, score
        if best is None:
            return {"topic": None, "subtopic": None, "confidence": 0.0}
        return {"topic": best.get("topic"), "subtopic": best.get("subtopic"), "confidence": round(best_score, 3)}
