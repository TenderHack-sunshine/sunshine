from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from time import perf_counter

from src.retrieval.bm25 import RussianBM25Retriever
from src.retrieval.official_dense import DenseUnavailable
from src.routing.normalization import normalize_query
from src.routing.technical import TechnicalRouter


def rrf_fuse(ranked_lists: list[list[dict]], k: int = 60, weights: list[float] | None = None) -> list[dict]:
    """Fuse retriever ranks only; raw BM25 and cosine values are never compared."""
    merged: dict[str, dict] = {}
    scores: defaultdict[str, float] = defaultdict(float)
    for list_index, results in enumerate(ranked_lists):
        weight = (weights or [1.0] * len(ranked_lists))[list_index]
        for position, result in enumerate(results, start=1):
            chunk_id = str(result["chunk_id"])
            merged[chunk_id] = result
            scores[chunk_id] += weight / (k + position)
    return [
        {**merged[chunk_id], "rrf_score": score, "score": score}
        for chunk_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ]


class TwoPathRetriever:
    """Dense official retrieval plus sparse tickets for technical troubleshooting."""

    def __init__(self, official: RussianBM25Retriever, tickets: RussianBM25Retriever, official_dense=None,
                 router: TechnicalRouter | None = None, official_dense_top_k: int = 15,
                 ticket_bm25_top_k: int = 15, final_candidates: int = 10, rrf_k: int = 60,
                 official_rrf_weight: float = 1.0, ticket_rrf_weight: float = 1.0):
        self.official = official
        self.tickets = tickets
        self.official_dense = official_dense
        self.router = router or TechnicalRouter()
        self.official_dense_top_k = official_dense_top_k
        self.ticket_bm25_top_k = ticket_bm25_top_k
        self.final_candidates = final_candidates
        self.rrf_k = rrf_k
        self.official_rrf_weight = official_rrf_weight
        self.ticket_rrf_weight = ticket_rrf_weight

    @classmethod
    def from_canonical(cls, chunks: list[dict], ticket_index: RussianBM25Retriever | None = None, official_dense=None, **kwargs):
        official = [chunk for chunk in chunks if chunk.get("source_type") != "support_ticket"]
        tickets = [chunk for chunk in chunks if chunk.get("source_type") == "support_ticket"]
        return cls(RussianBM25Retriever(official), ticket_index or RussianBM25Retriever(tickets), official_dense, **kwargs)

    def retrieve_with_trace(self, query: str, top_k: int | None = None, filters: dict[str, str | list[str]] | None = None,
                            technical: bool | None = None, max_per_ticket_document: int = 1) -> dict:
        total_started = perf_counter()
        normalized = normalize_query(query)
        decision = self.router.classify(normalized)
        use_tickets = bool(decision["technical"] if technical is None else technical)
        final_k = top_k or self.final_candidates
        trace = {
            "normalized_query": normalized, "route": decision, "dense_available": False, "fallback_used": False,
            "dense_error": None, "official_dense": [], "official_fallback": [], "ticket_bm25": [],
            "fused": [], "timing": {"query_embedding_ms": 0.0, "dense_search_ms": 0.0, "bm25_ms": 0.0, "fusion_ms": 0.0},
        }
        official: list[dict]
        if self.official_dense is not None:
            try:
                official = self.official_dense.retrieve(normalized, top_k=self.official_dense_top_k, filters=filters, max_per_document=2)
                trace["dense_available"] = True
                trace["official_dense"] = official
                trace["timing"].update(getattr(self.official_dense, "last_timing", {}))
            except (DenseUnavailable, RuntimeError, ConnectionError, OSError) as error:
                trace["dense_error"] = str(error)
                trace["fallback_used"] = True
                official = []
        else:
            trace["fallback_used"] = True
            official = []
        if not official:
            started = perf_counter()
            official = self.official.search(normalized, top_k=self.official_dense_top_k, filters=filters)
            trace["timing"]["bm25_ms"] += (perf_counter() - started) * 1000
            trace["official_fallback"] = official

        ranked_lists, rrf_weights = [official], [self.official_rrf_weight]
        if use_tickets:
            ticket_filters = dict(filters or {})
            ticket_filters["source_type"] = "support_ticket"
            started = perf_counter()
            tickets = self.tickets.search(normalized, top_k=self.ticket_bm25_top_k, filters=ticket_filters)
            trace["timing"]["bm25_ms"] += (perf_counter() - started) * 1000
            trace["ticket_bm25"] = tickets
            ranked_lists.append(tickets)
            rrf_weights.append(self.ticket_rrf_weight)
        started = perf_counter()
        fused = rrf_fuse(ranked_lists, k=self.rrf_k, weights=rrf_weights)
        trace["timing"]["fusion_ms"] = (perf_counter() - started) * 1000
        result, ticket_documents = [], defaultdict(int)
        for candidate in fused:
            if candidate["source_type"] == "support_ticket":
                document_id = str(candidate.get("document_id") or candidate["chunk_id"])
                if ticket_documents[document_id] >= max_per_ticket_document:
                    continue
                ticket_documents[document_id] += 1
            result.append(candidate)
            if len(result) == final_k:
                break
        trace["fused"] = fused
        trace["results"] = result
        trace["timing"]["total_retrieval_ms"] = (perf_counter() - total_started) * 1000
        return trace

    def search(self, *args, **kwargs) -> list[dict]:
        return self.retrieve_with_trace(*args, **kwargs)["results"]

    def retrieve(self, *args, **kwargs) -> list[dict]:
        return self.search(*args, **kwargs)


def load_two_path_retriever(canonical_path: str | Path, ticket_index_path: str | Path | None = None,
                            official_dense=None, **kwargs) -> TwoPathRetriever:
    from src.retrieval.canonical import read_jsonl

    chunks = list(read_jsonl(canonical_path))
    ticket_index = RussianBM25Retriever.load(ticket_index_path) if ticket_index_path else None
    return TwoPathRetriever.from_canonical(chunks, ticket_index=ticket_index, official_dense=official_dense, **kwargs)
