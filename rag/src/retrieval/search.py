from __future__ import annotations

from src.core.config import Settings
from .embedder import Embedder
from .hybrid import HybridRetriever
from .reranker import Reranker
from .vector_store import QdrantStore


def build_retriever(chunks: list[dict], settings: Settings, use_dense: bool = True) -> HybridRetriever:
    dense_store = embedder = None
    if use_dense:
        dense_store = QdrantStore(settings.qdrant_host, settings.qdrant_port, settings.qdrant_collection)
        embedder = Embedder(settings.embedding_model_path)
    return HybridRetriever(
        chunks, dense_store=dense_store, embedder=embedder, reranker=Reranker(settings.reranker_model_path),
        bm25_top_k=settings.bm25_top_k, dense_top_k=settings.dense_top_k, fusion_top_k=settings.fusion_top_k,
        final_top_k=settings.final_top_k, rrf_k=settings.rrf_k,
    )
