from __future__ import annotations

from pathlib import Path

from src.application.clarification import ClarificationPolicy
from src.application.evidence_sufficiency import EvidenceSufficiencyChecker
from src.application.pipeline import ConfidenceEvaluator, QueryPreprocessor, RAGService
from src.core.config import Settings
from src.generation.generator import ExtractiveGenerator
from src.generation.qwen import QwenGenerator, QwenGenerationClient
from src.retrieval.embeddings.persistent_worker import PersistentQwenEmbeddingClient
from src.retrieval.mvp import load_two_path_retriever
from src.retrieval.official_dense import DenseUnavailable, OfficialDenseRetriever
from src.retrieval.vector_store import HttpQdrantStore
from src.retrieval.reranker import Reranker
from src.retrieval.canonical import read_jsonl
from src.faq.cards import FAQStore
from src.retrieval.index_manifest import load_manifest, manifest_matches
from src.routing.intent import DomainLexicon
from src.routing.ticket_router import TicketRouter
from src.safety.profanity import build_profanity_detector


def official_dense_if_ready(settings: Settings):
    """Activate dense search only for a complete, official-only collection."""
    try:
        store = HttpQdrantStore(settings.qdrant_host, settings.qdrant_port, settings.qdrant_official_collection)
        official_chunks = [chunk for chunk in read_jsonl(settings.processed_dir / "index" / "all_chunks.jsonl")
                           if chunk.get("source_type") in OfficialDenseRetriever.official_source_types]
        manifest = load_manifest(settings.official_index_manifest_path)
        complete = manifest_matches(manifest, official_chunks, settings.qdrant_official_collection, store.count())
        # Compatibility only for installations indexed before manifests existed.
        if not complete and (manifest is not None or store.count() != settings.official_expected_points):
            return None
        return OfficialDenseRetriever(
            PersistentQwenEmbeddingClient(settings.dense_worker_host, settings.dense_worker_port, settings.dense_query_timeout_seconds),
            store,
            query_timeout_seconds=settings.dense_query_timeout_seconds,
        )
    except Exception:
        return None


class DeferredOfficialDenseRetriever:
    """Activate dense search automatically as soon as the Docker index is complete.

    Indexing runs independently so the frontend can answer through BM25 while
    Qdrant is filling.  The previous startup-only check required a manual RAG
    restart after indexing finished.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = HttpQdrantStore(settings.qdrant_host, settings.qdrant_port, settings.qdrant_official_collection)
        self.delegate = OfficialDenseRetriever(
            PersistentQwenEmbeddingClient(settings.dense_worker_host, settings.dense_worker_port,
                                          settings.dense_query_timeout_seconds),
            self.store,
            query_timeout_seconds=settings.dense_query_timeout_seconds,
        )
        self.official_chunks = [chunk for chunk in read_jsonl(settings.processed_dir / "index" / "all_chunks.jsonl")
                                if chunk.get("source_type") in OfficialDenseRetriever.official_source_types]

    @property
    def last_timing(self) -> dict:
        return self.delegate.last_timing

    def retrieve(self, *args, **kwargs):
        try:
            manifest = load_manifest(self.settings.official_index_manifest_path)
            complete = manifest_matches(manifest, self.official_chunks, self.settings.qdrant_official_collection, self.store.count())
            legacy_complete = manifest is None and self.store.count() == self.settings.official_expected_points
            if not self.store.collection_exists() or not (complete or legacy_complete):
                raise DenseUnavailable("official dense index is not complete")
        except DenseUnavailable:
            raise
        except Exception as error:
            raise DenseUnavailable(f"official dense index unavailable: {error}") from error
        return self.delegate.retrieve(*args, **kwargs)


def build_rag_service(settings: Settings | None = None, *, canonical_path: str | Path | None = None,
                      ticket_index_path: str | Path | None = None, official_dense=None, reranker=None) -> RAGService:
    settings = settings or Settings()
    profanity_detector = build_profanity_detector(settings.profanity_backend)
    canonical_path = Path(canonical_path or settings.processed_dir / "index" / "all_chunks.jsonl")
    ticket_index_path = Path(ticket_index_path or settings.data_dir / "indexes" / "support_tickets_bm25.pkl")
    dense = official_dense if official_dense is not None else DeferredOfficialDenseRetriever(settings)
    retriever = load_two_path_retriever(canonical_path, ticket_index_path, official_dense=dense, final_candidates=settings.final_top_k, rrf_k=settings.rrf_k,
                                        official_dense_top_k=settings.dense_top_k, official_bm25_top_k=settings.bm25_top_k,
                                        official_rrf_weight=settings.official_rrf_weight, ticket_rrf_weight=settings.ticket_rrf_weight,
                                        dense_fusion_weight=settings.dense_fusion_weight,
                                        bm25_fusion_weight=settings.bm25_fusion_weight,
                                        retrieval_strategy=settings.retrieval_strategy,
                                        dense_primary_min_score=settings.dense_primary_min_score,
                                        dense_primary_min_agreement=settings.dense_primary_min_agreement,
                                        dense_primary_keep_top_k=settings.dense_primary_keep_top_k,
                                        bm25_rescue_top_k=settings.bm25_rescue_top_k)
    reranker = reranker if reranker is not None else Reranker(settings.reranker_model_path)
    clarification_policy = ClarificationPolicy(enabled=settings.clarification_policy_enabled,
                                               short_failure_max_tokens=settings.clarification_short_failure_max_tokens,
                                               broad_policy_max_tokens=settings.clarification_broad_policy_max_tokens)
    if settings.generator_backend == "qwen":
        generator = QwenGenerator(
            QwenGenerationClient(settings.generation_worker_host, settings.generation_worker_port,
                                 settings.generation_timeout_seconds, settings.generation_ollama_model),
            model_name=settings.generation_model_name,
            max_new_tokens=settings.generation_max_new_tokens,
            max_seconds=settings.generation_max_seconds,
            max_context_chars=settings.generation_max_context_chars,
            max_evidence_chunks=settings.generation_max_evidence_chunks,
            allow_extractive_fallback=settings.allow_extractive_generation_fallback,
        )
    else:
        generator = ExtractiveGenerator(settings.min_evidence_score)
    # Tests and first-run deployments may not have built the canonical file
    # yet.  In that state there can be no valid source-linked FAQ answer, so
    # an empty store is the safe, non-blocking choice.
    canonical_chunks = list(read_jsonl(canonical_path)) if canonical_path.is_file() else []
    faq_store = FAQStore.from_jsonl(settings.faq_cards_path, canonical_chunks)
    lexicon = DomainLexicon.from_chunks(canonical_chunks)
    return RAGService(retriever, preprocessor=QueryPreprocessor(profanity_detector), clarification_policy=clarification_policy,
                      reranker=reranker, rerank_enabled=settings.rerank_enabled,
                      confidence=ConfidenceEvaluator(settings.confidence_min_sources, settings.confidence_min_official_score,
                                                     settings.confidence_min_agreement), final_top_k=settings.final_top_k,
                      rerank_top_n=settings.hybrid_rerank_top_n, evidence_max_per_document=settings.evidence_max_per_document,
                      evidence_sufficiency=EvidenceSufficiencyChecker(enabled=settings.evidence_sufficiency_enabled), generator=generator,
                      faq_store=faq_store, lexicon=lexicon, ticket_router=TicketRouter(canonical_chunks))
