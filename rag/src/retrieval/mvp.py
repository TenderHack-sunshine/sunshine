from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from src.retrieval.bm25 import RussianBM25Retriever
from src.routing.normalization import normalize_query
from src.routing.technical import TechnicalRouter


def rrf_fuse(ranked_lists: list[tuple[list[dict], float]], k: int = 60) -> list[dict]:
    """Combine ranks, never raw BM25 and cosine scores, with authority weighting."""
    merged: dict[str, dict] = {}
    scores: defaultdict[str, float] = defaultdict(float)
    for results, weight in ranked_lists:
        for rank, result in enumerate(results, start=1):
            chunk_id = str(result["chunk_id"])
            merged[chunk_id] = result
            scores[chunk_id] += weight / (k + rank)
    return [{**merged[chunk_id], "score": score} for chunk_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)]


class TwoPathRetriever:
    """Official evidence first; historical tickets only supplement technical queries."""

    def __init__(self, official: RussianBM25Retriever, tickets: RussianBM25Retriever,
                 official_dense=None, router: TechnicalRouter | None = None):
        self.official = official
        self.tickets = tickets
        self.official_dense = official_dense
        self.router = router or TechnicalRouter()

    @classmethod
    def from_canonical(cls, chunks: list[dict], ticket_index: RussianBM25Retriever | None = None, official_dense=None):
        official = [chunk for chunk in chunks if chunk.get("source_type") != "support_ticket"]
        tickets = [chunk for chunk in chunks if chunk.get("source_type") == "support_ticket"]
        return cls(RussianBM25Retriever(official), ticket_index or RussianBM25Retriever(tickets), official_dense)

    def search(self, query: str, top_k: int = 10, filters: dict[str, str | list[str]] | None = None,
               technical: bool | None = None, max_per_ticket_document: int = 1) -> list[dict]:
        normalized = normalize_query(query)
        decision = self.router.classify(normalized)
        use_tickets = decision["technical"] if technical is None else technical
        if self.official_dense is not None:
            official = [
                {
                    "chunk_id": item.get("chunk_id"), "document_id": item.get("document_id"), "text": item.get("text", ""),
                    "source_type": item.get("source_type"), "authority": item.get("authority"), "score": float(item.get("score", 0)),
                    "retrieval_method": "dense", "metadata": dict(item.get("metadata") or {}),
                    "source_path": item.get("source_path"), "title": item.get("title"), "section": item.get("section"),
                    "page_start": item.get("page_start"), "page_end": item.get("page_end"),
                }
                for item in self.official_dense.retrieve(normalized, top_k=top_k * 3, filters=filters, max_per_document=2)
            ]
        else:
            official = self.official.search(normalized, top_k=top_k * 3, filters=filters)
        ranked_lists: list[tuple[list[dict], float]] = [(official, 1.2)]
        if use_tickets:
            ticket_filters = dict(filters or {})
            ticket_filters["source_type"] = "support_ticket"
            tickets = self.tickets.search(normalized, top_k=top_k * 5, filters=ticket_filters)
            ranked_lists.append((tickets, 1.0))
        fused = rrf_fuse(ranked_lists)
        result, ticket_documents = [], defaultdict(int)
        for candidate in fused:
            if candidate["source_type"] == "support_ticket":
                document_id = str(candidate.get("document_id") or candidate["chunk_id"])
                if ticket_documents[document_id] >= max_per_ticket_document:
                    continue
                ticket_documents[document_id] += 1
            result.append(candidate)
            if len(result) == top_k:
                break
        # Technical troubleshooting needs at least one case-history signal to be
        # observable, while the stronger official RRF rank retains first priority.
        if use_tickets and not any(item["source_type"] == "support_ticket" for item in result):
            ticket_candidate = next((item for item in fused if item["source_type"] == "support_ticket"), None)
            if ticket_candidate is not None:
                if len(result) >= top_k:
                    result[-1] = ticket_candidate
                else:
                    result.append(ticket_candidate)
        return result

    def retrieve(self, *args, **kwargs):
        return self.search(*args, **kwargs)


def load_two_path_retriever(canonical_path: str | Path, ticket_index_path: str | Path | None = None) -> TwoPathRetriever:
    from src.retrieval.canonical import read_jsonl

    chunks = list(read_jsonl(canonical_path))
    ticket_index = RussianBM25Retriever.load(ticket_index_path) if ticket_index_path else None
    return TwoPathRetriever.from_canonical(chunks, ticket_index=ticket_index)
