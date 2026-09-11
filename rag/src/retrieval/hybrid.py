from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .bm25 import BM25Index


def reciprocal_rank_fusion(result_lists: Iterable[list[dict]], k: int = 60) -> list[dict]:
    """Fuse ranked result lists by stable chunk id, without mixing score scales."""
    merged: dict[str, dict] = {}
    scores: defaultdict[str, float] = defaultdict(float)
    for results in result_lists:
        for rank, document in enumerate(results, start=1):
            doc_id = str(document.get("chunk_id") or document.get("id"))
            if not doc_id:
                continue
            merged[doc_id] = document
            scores[doc_id] += 1.0 / (k + rank)
    return [{**merged[doc_id], "score": score} for doc_id, score in sorted(scores.items(), key=lambda pair: pair[1], reverse=True)]


class HybridRetriever:
    """BM25 + dense retrieval, RRF, optional reranking, and authority-aware output."""

    def __init__(self, documents: list[dict], dense_store=None, embedder=None, reranker=None,
                 bm25_top_k: int = 20, dense_top_k: int = 20, fusion_top_k: int = 20, final_top_k: int = 5, rrf_k: int = 60):
        self.documents = documents
        self.bm25 = BM25Index(documents)
        self.dense_store, self.embedder, self.reranker = dense_store, embedder, reranker
        self.bm25_top_k, self.dense_top_k = bm25_top_k, dense_top_k
        self.fusion_top_k, self.final_top_k, self.rrf_k = fusion_top_k, final_top_k, rrf_k

    @staticmethod
    def normalize_query(query: str) -> str:
        return " ".join(query.split())

    @staticmethod
    def _authority_adjustment(document: dict) -> float:
        if document.get("authority") == "manual":
            return 0.002
        if document.get("answer_quality") == "low":
            return -0.008
        return 0.0

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        query = self.normalize_query(query)
        if not query:
            return []
        bm25_results = self.bm25.search(query, self.bm25_top_k)
        result_lists = [bm25_results]
        if self.dense_store is not None and self.embedder is not None:
            try:
                result_lists.append(self.dense_store.search(self.embedder.embed_query(query), self.dense_top_k))
            except (RuntimeError, ConnectionError, OSError):
                # Dense infrastructure is optional; lexical local retrieval remains available.
                pass
        fused = reciprocal_rank_fusion(result_lists, self.rrf_k)[:self.fusion_top_k]
        for document in fused:
            document["score"] += self._authority_adjustment(document)
        fused.sort(key=lambda item: item["score"], reverse=True)
        final_k = top_k or self.final_top_k
        if self.reranker is not None:
            fused = self.reranker.rerank(query, fused, top_k=final_k)
        else:
            fused = fused[:final_k]
        return [self._result_format(document) for document in fused]

    @staticmethod
    def _result_format(document: dict) -> dict:
        return {
            "score": float(document.get("score", 0.0)), "text": document.get("text", ""),
            "source": document.get("source", "unknown"), "page": document.get("page", document.get("page_start")),
            "section": document.get("section"), "authority": document.get("authority", "manual"),
            "chunk_id": document.get("chunk_id"),
        }
