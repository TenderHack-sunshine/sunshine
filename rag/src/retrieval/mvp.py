from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from time import perf_counter

from src.retrieval.bm25 import RussianBM25Retriever
from src.retrieval.official_dense import DenseUnavailable
from src.routing.normalization import normalize_query
from src.routing.technical import TechnicalRouter


RETRIEVAL_STRATEGIES = {"dense_primary", "hybrid_rrf", "bm25_only"}


def rrf_fuse(ranked_lists: list[list[dict]], k: int = 60, weights: list[float] | None = None) -> list[dict]:
    """Fuse retriever ranks only; raw BM25 and cosine values are never compared."""
    if k <= 0:
        raise ValueError("RRF k must be a positive integer")
    if weights is None:
        effective_weights = [1.0] * len(ranked_lists)
    else:
        if len(weights) != len(ranked_lists):
            raise ValueError("RRF weights must have one value per ranked list")
        if any(weight < 0 for weight in weights):
            raise ValueError("RRF weights must be non-negative")
        effective_weights = weights
    merged: dict[str, dict] = {}
    scores: defaultdict[str, float] = defaultdict(float)
    contributors: defaultdict[str, list[str]] = defaultdict(list)
    for list_index, results in enumerate(ranked_lists):
        weight = effective_weights[list_index]
        for position, result in enumerate(results, start=1):
            chunk_id = str(result["chunk_id"])
            merged[chunk_id] = result
            scores[chunk_id] += weight / (k + position)
            contributors[chunk_id].append(str(result.get("retrieval_method", "unknown")))
    return [
        {**merged[chunk_id], "retrieval_method": "hybrid" if len(set(contributors[chunk_id])) > 1 else merged[chunk_id].get("retrieval_method"),
         "retrieval_methods": sorted(set(contributors[chunk_id])), "rrf_score": score, "score": score}
        for chunk_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ]


class TwoPathRetriever:
    """Official dense retrieval with configurable sparse rescue/fallback modes."""

    def __init__(self, official: RussianBM25Retriever, tickets: RussianBM25Retriever, official_dense=None,
                 router: TechnicalRouter | None = None, official_dense_top_k: int = 15,
                 official_bm25_top_k: int = 20, ticket_bm25_top_k: int = 15, final_candidates: int = 10, rrf_k: int = 60,
                 official_rrf_weight: float = 1.0, ticket_rrf_weight: float = 1.0,
                 dense_fusion_weight: float = 1.0, bm25_fusion_weight: float = 1.0,
                 retrieval_strategy: str = "dense_primary", dense_primary_min_score: float = 0.55,
                 dense_primary_min_agreement: float = 0.0, dense_primary_keep_top_k: int = 3,
                 bm25_rescue_top_k: int = 3):
        strategy = retrieval_strategy.strip().lower()
        if strategy not in RETRIEVAL_STRATEGIES:
            raise ValueError(f"Unsupported retrieval strategy: {retrieval_strategy}")
        if dense_primary_keep_top_k < 1 or bm25_rescue_top_k < 1:
            raise ValueError("Dense-primary keep/rescue top-k values must be positive")
        self.official = official
        self.tickets = tickets
        self.official_dense = official_dense
        self.router = router or TechnicalRouter()
        self.official_dense_top_k = official_dense_top_k
        self.official_bm25_top_k = official_bm25_top_k
        self.ticket_bm25_top_k = ticket_bm25_top_k
        self.final_candidates = final_candidates
        self.rrf_k = rrf_k
        self.official_rrf_weight = official_rrf_weight
        self.ticket_rrf_weight = ticket_rrf_weight
        self.dense_fusion_weight = dense_fusion_weight
        self.bm25_fusion_weight = bm25_fusion_weight
        self.retrieval_strategy = strategy
        self.dense_primary_min_score = dense_primary_min_score
        self.dense_primary_min_agreement = dense_primary_min_agreement
        self.dense_primary_keep_top_k = dense_primary_keep_top_k
        self.bm25_rescue_top_k = bm25_rescue_top_k

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
            "dense_error": None, "official_dense": [], "official_bm25": [], "official_fallback": [], "ticket_bm25": [], "hybrid": [],
            "fused": [], "timing": {"query_embedding_ms": 0.0, "dense_search_ms": 0.0, "bm25_ms": 0.0, "fusion_ms": 0.0},
            "retrieval_strategy": self.retrieval_strategy.upper(), "dense_primary_used": False,
            "bm25_rescue_used": False, "bm25_fallback_used": False,
        }
        # Official lexical retrieval is always part of the active path; dense augments it.
        started = perf_counter()
        official_bm25 = self.official.search(normalized, top_k=self.official_bm25_top_k, filters=filters)
        trace["timing"]["bm25_ms"] += (perf_counter() - started) * 1000
        trace["official_bm25"] = official_bm25
        dense: list[dict] = []
        if self.official_dense is not None:
            try:
                dense = self.official_dense.retrieve(normalized, top_k=self.official_dense_top_k, filters=filters, max_per_document=2)
                trace["dense_available"] = bool(dense)
                trace["official_dense"] = dense
                trace["timing"].update(getattr(self.official_dense, "last_timing", {}))
            except (DenseUnavailable, RuntimeError, ConnectionError, OSError) as error:
                trace["dense_error"] = str(error)
                trace["fallback_used"] = True
                dense = []
        else:
            trace["fallback_used"] = True
        tickets: list[dict] = []
        if use_tickets:
            ticket_filters = dict(filters or {})
            ticket_filters["source_type"] = "support_ticket"
            started = perf_counter()
            tickets = self.tickets.search(normalized, top_k=self.ticket_bm25_top_k, filters=ticket_filters)
            trace["timing"]["bm25_ms"] += (perf_counter() - started) * 1000
            trace["ticket_bm25"] = tickets

        started = perf_counter()
        if self.retrieval_strategy == "bm25_only" or not dense:
            if not dense:
                trace["fallback_used"] = True
                trace["bm25_fallback_used"] = self.retrieval_strategy != "bm25_only"
                trace["official_fallback"] = official_bm25
            sparse_lists = [official_bm25, *([tickets] if tickets else [])]
            sparse_weights = [self.official_rrf_weight * self.bm25_fusion_weight,
                              *([self.ticket_rrf_weight * self.bm25_fusion_weight] if tickets else [])]
            fused = rrf_fuse(sparse_lists, k=self.rrf_k, weights=sparse_weights)
            retrieval_mode = "BM25_FALLBACK" if not dense and self.retrieval_strategy != "bm25_only" else "BM25_ONLY"
        elif self.retrieval_strategy == "hybrid_rrf":
            official_bm25_weight = self.official_rrf_weight * self.bm25_fusion_weight
            dense_weight = self.official_rrf_weight * self.dense_fusion_weight
            ticket_weight = self.ticket_rrf_weight * self.bm25_fusion_weight
            ranked_lists = [official_bm25, dense, *([tickets] if tickets else [])]
            rrf_weights = [official_bm25_weight, dense_weight, *([ticket_weight] if tickets else [])]
            trace["hybrid"] = rrf_fuse([official_bm25, dense], k=self.rrf_k, weights=[official_bm25_weight, dense_weight])
            fused = rrf_fuse(ranked_lists, k=self.rrf_k, weights=rrf_weights)
            retrieval_mode = "HYBRID"
        else:
            trace["dense_primary_used"] = True
            dense_documents = {str(item.get("document_id") or item.get("chunk_id")) for item in dense[:self.dense_primary_keep_top_k]}
            bm25_documents = {str(item.get("document_id") or item.get("chunk_id")) for item in official_bm25}
            agreement = len(dense_documents & bm25_documents) / max(min(len(dense_documents), len(bm25_documents)), 1)
            top_dense_score = float(dense[0].get("raw_score", dense[0].get("score", 0.0))) if dense else 0.0
            dense_is_strong = bool(dense and dense[0].get("authority") == "official" and top_dense_score >= self.dense_primary_min_score
                                   and agreement >= self.dense_primary_min_agreement)
            fused = list(dense)
            if not dense_is_strong:
                rescue, known_chunks, rescue_documents = [], {item.get("chunk_id") for item in dense[:self.dense_primary_keep_top_k]}, set(dense_documents)
                for item in [*official_bm25[:self.bm25_rescue_top_k], *tickets[:self.bm25_rescue_top_k]]:
                    document_id = str(item.get("document_id") or item.get("chunk_id"))
                    if item.get("chunk_id") in known_chunks or document_id in rescue_documents:
                        continue
                    rescue.append(item)
                    known_chunks.add(item.get("chunk_id"))
                    rescue_documents.add(document_id)
                if rescue:
                    trace["bm25_rescue_used"] = True
                    fused = [*dense[:self.dense_primary_keep_top_k], *rescue, *dense[self.dense_primary_keep_top_k:]]
                    seen_chunks: set[str] = set()
                    fused = [item for item in fused if not (str(item.get("chunk_id")) in seen_chunks or seen_chunks.add(str(item.get("chunk_id"))))]
            retrieval_mode = "DENSE_PRIMARY_RESCUE" if trace["bm25_rescue_used"] else "DENSE_PRIMARY"
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
        trace["retrieval_mode"] = retrieval_mode
        trace["dense_candidates"] = len(dense)
        trace["bm25_candidates"] = len(official_bm25) + len(trace["ticket_bm25"])
        trace["hybrid_candidates"] = len(trace["hybrid"])
        trace["final_candidates"] = len(result)
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
