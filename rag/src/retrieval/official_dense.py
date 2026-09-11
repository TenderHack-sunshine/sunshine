from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from time import perf_counter


class DenseUnavailable(RuntimeError):
    """Dense retrieval cannot serve this request; the caller must use fallback."""


class OfficialDenseRetriever:
    """Qwen3 + Qdrant retriever restricted to authoritative official sources."""

    official_source_types = ("official_kb", "official_manual", "support_taxonomy")

    def __init__(self, embedder, store, query_timeout_seconds: float | None = 12.0):
        self.embedder = embedder
        self.store = store
        self.query_timeout_seconds = query_timeout_seconds
        self.last_timing = {"query_embedding_ms": 0.0, "dense_search_ms": 0.0}

    def _with_timeout(self, callable_):
        if self.query_timeout_seconds is None:
            return callable_()
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(callable_)
        try:
            return future.result(timeout=self.query_timeout_seconds)
        except FutureTimeout as error:
            raise DenseUnavailable(f"query embedding timed out after {self.query_timeout_seconds}s") from error
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def retrieve(self, query: str, top_k: int = 15, filters: dict[str, str | list[str]] | None = None,
                 max_per_document: int | None = 2) -> list[dict]:
        if not query.strip():
            return []
        merged_filters = dict(filters or {})
        requested = merged_filters.get("source_type")
        allowed = set(self.official_source_types)
        if requested is not None:
            requested_values = set(requested if isinstance(requested, list) else [requested])
            allowed &= requested_values
        if not allowed:
            return []
        merged_filters["source_type"] = sorted(allowed)
        try:
            embedding_started = perf_counter()
            vector = self._with_timeout(lambda: self.embedder.embed_query(query))
            self.last_timing["query_embedding_ms"] = (perf_counter() - embedding_started) * 1000
            search_started = perf_counter()
            raw = self.store.search(vector, limit=top_k * 3, filters=merged_filters)
            self.last_timing["dense_search_ms"] = (perf_counter() - search_started) * 1000
        except DenseUnavailable:
            raise
        except Exception as error:  # Qdrant/network/model errors are an explicit controlled fallback signal.
            raise DenseUnavailable(str(error)) from error

        selected, document_counts = [], {}
        for item in raw:
            if item.get("source_type") not in self.official_source_types:
                # Defense in depth: a misconfigured collection must never leak tickets.
                continue
            document_id = str(item.get("document_id") or item.get("chunk_id"))
            if max_per_document is not None and document_counts.get(document_id, 0) >= max_per_document:
                continue
            document_counts[document_id] = document_counts.get(document_id, 0) + 1
            selected.append({
                "chunk_id": item.get("chunk_id"), "document_id": item.get("document_id"), "text": item.get("text", ""),
                "source_type": item.get("source_type"), "authority": item.get("authority"),
                "retrieval_method": "dense", "raw_score": float(item.get("score", 0.0)), "rank": len(selected) + 1,
                "metadata": dict(item.get("metadata") or {}), "source_path": item.get("source_path"),
                "title": item.get("title"), "section": item.get("section"),
                "page_start": item.get("page_start"), "page_end": item.get("page_end"),
            })
            if len(selected) == top_k:
                break
        return selected
