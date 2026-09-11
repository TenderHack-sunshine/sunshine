from __future__ import annotations

from pathlib import Path

from src.application.pipeline import ConfidenceEvaluator, RAGService
from src.core.config import Settings
from src.retrieval.embeddings.isolated_qwen3 import IsolatedQwen3QueryEmbedding
from src.retrieval.mvp import load_two_path_retriever
from src.retrieval.official_dense import OfficialDenseRetriever
from src.retrieval.vector_store import HttpQdrantStore


def official_dense_if_ready(settings: Settings):
    """Activate dense search only for a complete, official-only collection."""
    try:
        store = HttpQdrantStore(settings.qdrant_host, settings.qdrant_port, settings.qdrant_official_collection)
        if not store.collection_exists() or store.count() != settings.official_expected_points:
            return None
        return OfficialDenseRetriever(
            IsolatedQwen3QueryEmbedding(settings.embedding_model_path, settings.dense_query_timeout_seconds),
            store,
            query_timeout_seconds=settings.dense_query_timeout_seconds,
        )
    except Exception:
        return None


def build_rag_service(settings: Settings | None = None, *, canonical_path: str | Path | None = None,
                      ticket_index_path: str | Path | None = None, official_dense=None, reranker=None) -> RAGService:
    settings = settings or Settings()
    canonical_path = Path(canonical_path or settings.processed_dir / "index" / "all_chunks.jsonl")
    ticket_index_path = Path(ticket_index_path or settings.data_dir / "indexes" / "support_tickets_bm25.pkl")
    dense = official_dense if official_dense is not None else official_dense_if_ready(settings)
    retriever = load_two_path_retriever(canonical_path, ticket_index_path, official_dense=dense, final_candidates=settings.final_top_k, rrf_k=settings.rrf_k,
                                        official_rrf_weight=settings.official_rrf_weight, ticket_rrf_weight=settings.ticket_rrf_weight)
    return RAGService(retriever, reranker=reranker, rerank_enabled=settings.rerank_enabled,
                      confidence=ConfidenceEvaluator(settings.confidence_min_sources), final_top_k=settings.final_top_k)
