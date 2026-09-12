from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from src.generation.generator import EvidenceGenerator
from src.application.evidence import compact_evidence, tagged_context
from src.moderation.profanity import detect_profanity
from src.routing.normalization import normalize_query
from src.routing.technical import TechnicalRouter


PROFANITY_MESSAGE = "В вашем сообщении используется нецензурная лексика. Пожалуйста, переформулируйте вопрос без неё, и я постараюсь помочь."
CLARIFICATION_MESSAGE = "Уточните, пожалуйста, что именно не работает и на каком этапе возникает проблема?"
OPERATOR_MESSAGE = "Недостаточно надёжных сведений для ответа. Передаю обращение оператору поддержки."


@dataclass(frozen=True)
class QueryPreprocessor:
    def process(self, query: str) -> dict:
        moderation = detect_profanity(query)
        return {"original_query": query, "moderation": moderation, "normalized_query": None if moderation["contains_profanity"] else normalize_query(query)}


class SupportRouter:
    """Deterministic three-level router; technical issues bypass L1/L2."""

    l2_markers = ("регламент", "правил", "требован", "норматив", "методолог", "порядок", "услови")

    def __init__(self, technical_router: TechnicalRouter | None = None):
        self.technical_router = technical_router or TechnicalRouter()

    def classify(self, query: str) -> dict:
        technical = self.technical_router.classify(query)
        if technical["technical"]:
            return {"route": "L3", "technical": True, "reason": technical["markers"]}
        markers = [marker for marker in self.l2_markers if marker in query]
        return {"route": "L2" if markers else "L1", "technical": False, "reason": markers}


class ContextAnalyzer:
    """Reject only very short, context-free failure reports before retrieval."""

    incomplete = {"не работает", "ошибка", "не могу войти", "не входит", "не получается"}

    def needs_clarification(self, normalized_query: str) -> bool:
        compact = " ".join(normalized_query.split())
        return compact in self.incomplete


class NoopReranker:
    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        return candidates[:top_k]


class ConfidenceEvaluator:
    """Transparent thresholds, deliberately not an invented probability."""

    def __init__(self, min_sources: int = 1, min_official_score: float = 0.0, min_agreement: float = 0.0):
        self.min_sources = min_sources
        self.min_official_score = min_official_score
        self.min_agreement = min_agreement

    def features(self, candidates: list[dict], trace: dict) -> dict:
        scores = [float(item.get("reranker_score", item.get("rrf_score", item.get("score", 0.0)))) for item in candidates]
        official = [item for item in candidates if item.get("authority") == "official"]
        tickets = [item for item in candidates if item.get("source_type") == "support_ticket"]
        bm25_ids = {item.get("chunk_id") for item in trace.get("official_bm25", [])}
        dense_ids = {item.get("chunk_id") for item in trace.get("official_dense", [])}
        overlap = len(bm25_ids & dense_ids)
        agreement = overlap / max(min(len(bm25_ids), len(dense_ids)), 1) if dense_ids else 0.0
        return {
            "top_score": scores[0] if scores else 0.0,
            "top_reranker_score": next((float(item["reranker_score"]) for item in candidates if "reranker_score" in item), None),
            "num_relevant_candidates": len(candidates), "num_official_candidates": len(official), "num_ticket_candidates": len(tickets),
            "official_evidence_present": bool(official), "top1_top2_gap": scores[0] - scores[1] if len(scores) > 1 else scores[0] if scores else 0.0,
            "retrieval_agreement": agreement,
        }

    def decide(self, route: str, candidates: list[dict], features: dict | None = None) -> tuple[str, str | None]:
        features = features or self.features(candidates, {})
        if len(candidates) < self.min_sources:
            return "ESCALATE_TO_OPERATOR", "no_relevant_evidence"
        official = features["official_evidence_present"]
        ticket = features["num_ticket_candidates"] > 0
        if official and features["top_score"] < self.min_official_score:
            return "ESCALATE_TO_OPERATOR", "official_score_below_threshold"
        if official and self.min_agreement > 0 and features["retrieval_agreement"] < self.min_agreement:
            return "NEEDS_CLARIFICATION", "official_retrieval_agreement_below_threshold"
        if features["retrieval_agreement"] < self.min_agreement and not official:
            return "ESCALATE_TO_OPERATOR", "weak_retrieval_agreement"
        if route == "L3" and not (official or ticket):
            return "ESCALATE_TO_OPERATOR", "no_support_evidence"
        return "ANSWER", None


class RAGService:
    """Orchestrates guards, routing, swappable retrieval/reranking and evidence output."""

    def __init__(self, retriever, *, preprocessor: QueryPreprocessor | None = None, router: SupportRouter | None = None,
                 context: ContextAnalyzer | None = None, reranker=None, rerank_enabled: bool = False,
                 generator=None, confidence: ConfidenceEvaluator | None = None, final_top_k: int = 5, rerank_top_n: int = 20,
                 evidence_max_per_document: int = 2):
        self.retriever = retriever
        self.preprocessor = preprocessor or QueryPreprocessor()
        self.router = router or SupportRouter()
        self.context = context or ContextAnalyzer()
        self.reranker = reranker or NoopReranker()
        self.rerank_enabled = rerank_enabled
        self.generator = generator or EvidenceGenerator()
        self.confidence = confidence or ConfidenceEvaluator()
        self.final_top_k = final_top_k
        self.rerank_top_n = rerank_top_n
        self.evidence_max_per_document = evidence_max_per_document

    def ask(self, query: str) -> dict:
        started = perf_counter()
        prepared = self.preprocessor.process(query)
        base = {"original_query": query, "normalized_query": prepared["normalized_query"], "sources": []}
        if prepared["moderation"]["contains_profanity"]:
            return {**base, "status": "REFUSE_PROFANITY", "route": None, "answer": PROFANITY_MESSAGE,
                    "diagnostics": {"profanity_detected": True, "dense_available": False, "fallback_used": False, "retrieval_mode": "NONE", "retrieved_count": 0, "reranker_used": False,
                                    "retrieval_strategy": "NONE", "dense_primary_used": False, "bm25_rescue_used": False, "bm25_fallback_used": False,
                                    "timings_ms": {"total": (perf_counter() - started) * 1000}}}
        normalized = prepared["normalized_query"]
        assert normalized is not None
        if self.context.needs_clarification(normalized):
            return {**base, "status": "NEEDS_CLARIFICATION", "route": None, "answer": CLARIFICATION_MESSAGE,
                    "diagnostics": {"profanity_detected": False, "dense_available": False, "fallback_used": False, "retrieval_mode": "NONE", "retrieved_count": 0, "reranker_used": False,
                                    "retrieval_strategy": "NONE", "dense_primary_used": False, "bm25_rescue_used": False, "bm25_fallback_used": False,
                                    "timings_ms": {"total": (perf_counter() - started) * 1000}}}
        route = self.router.classify(normalized)
        trace = self.retriever.retrieve_with_trace(normalized, technical=route["technical"])
        candidates = trace["results"]
        reranker_used = False
        reranker_available = bool(getattr(self.reranker, "available", self.rerank_enabled))
        if self.rerank_enabled and reranker_available:
            try:
                candidates = self.reranker.rerank(normalized, candidates[:self.rerank_top_n], self.final_top_k)
                reranker_used = True
            except Exception as error:
                trace["reranker_error"] = str(error)
                candidates = candidates[:self.final_top_k]
        else:
            candidates = candidates[:self.final_top_k]
        candidates = compact_evidence(candidates, max_per_document=self.evidence_max_per_document)
        features = self.confidence.features(candidates, trace)
        status, reason = self.confidence.decide(route["route"], candidates, features)
        generated = self.generator.answer(candidates) if status == "ANSWER" else {"answer": OPERATOR_MESSAGE, "used_evidence": False}
        sources = [{key: item.get(key) for key in ("chunk_id", "document_id", "source_type", "authority", "source_path", "title", "section", "page_start", "page_end", "retrieval_method", "raw_score", "rrf_score", "metadata")} for item in candidates]
        timings = dict(trace.get("timing", {}))
        timings["total"] = (perf_counter() - started) * 1000
        return {**base, "status": status, "route": route["route"], "answer": generated["answer"], "sources": sources,
                "diagnostics": {"profanity_detected": False, "dense_available": trace.get("dense_available", False), "fallback_used": trace.get("fallback_used", False),
                                "retrieval_mode": trace.get("retrieval_mode", "BM25_ONLY"), "dense_candidates": trace.get("dense_candidates", 0),
                                "bm25_candidates": trace.get("bm25_candidates", 0), "hybrid_candidates": trace.get("hybrid_candidates", 0),
                                "final_candidates": trace.get("final_candidates", len(candidates)),
                                "retrieval_strategy": trace.get("retrieval_strategy", "BM25_ONLY"),
                                "dense_primary_used": trace.get("dense_primary_used", False),
                                "bm25_rescue_used": trace.get("bm25_rescue_used", False),
                                "bm25_fallback_used": trace.get("bm25_fallback_used", False),
                                "retrieved_count": len(candidates), "reranker_enabled": self.rerank_enabled, "reranker_available": reranker_available,
                                "reranker_used": reranker_used, "reranker_latency_ms": float(getattr(self.reranker, "last_latency_ms", 0.0)),
                                "reranker_candidates": min(len(trace["results"]), self.rerank_top_n) if self.rerank_enabled else 0,
                                "confidence": features, "confidence_reason": reason, "context": tagged_context(candidates),
                                "timings_ms": timings}}
