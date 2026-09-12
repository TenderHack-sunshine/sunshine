from __future__ import annotations

from pathlib import Path
from time import perf_counter


class Reranker:
    """Optional local cross-encoder reranker; retrieval works when it is absent."""

    def __init__(self, model_path: str | Path | None = None):
        self.model_path = Path(model_path) if model_path else None
        self._model = None
        self.last_latency_ms = 0.0

    @property
    def available(self) -> bool:
        return self.model_path is not None and self.model_path.exists()

    def _load(self):
        if not self.available:
            return None
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(str(self.model_path), local_files_only=True)
        return self._model

    def rerank(self, query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
        model = self._load()
        if model is None:
            return documents[:top_k]
        started = perf_counter()
        scores = model.predict([(query, document["text"]) for document in documents])
        self.last_latency_ms = (perf_counter() - started) * 1000
        ranked = [{**document, "reranker_score": float(score), "score": float(score)} for document, score in zip(documents, scores)]
        return sorted(ranked, key=lambda item: item["score"], reverse=True)[:top_k]
