from __future__ import annotations


class DenseRetriever:
    """Qwen3 query embedding plus Qdrant cosine retrieval, without reranking."""

    def __init__(self, embedder, store, max_per_document: int | None = 2):
        self.embedder = embedder
        self.store = store
        self.max_per_document = max_per_document

    def retrieve(self, query: str, top_k: int = 10, filters: dict[str, str | list[str]] | None = None,
                 max_per_document: int | None = None) -> list[dict]:
        if not query or not query.strip() or top_k <= 0:
            return []
        limit = max(top_k, top_k * 4) if (max_per_document if max_per_document is not None else self.max_per_document) else top_k
        candidates = self.store.search(self.embedder.embed_query(query.strip()), limit=limit, filters=filters)
        repeated_limit = self.max_per_document if max_per_document is None else max_per_document
        if repeated_limit is None:
            return candidates[:top_k]
        selected, per_document = [], {}
        for result in candidates:
            document_id = str(result.get("document_id") or result.get("chunk_id"))
            if per_document.get(document_id, 0) >= repeated_limit:
                continue
            per_document[document_id] = per_document.get(document_id, 0) + 1
            selected.append(result)
            if len(selected) == top_k:
                break
        return selected
