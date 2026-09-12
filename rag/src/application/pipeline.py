from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from src.generation.generator import EvidenceGenerator
from src.application.clarification import ClarificationPolicy, ConfidenceSignals
from src.application.evidence import compact_evidence, tagged_context
from src.application.evidence_sufficiency import EvidenceSufficiencyChecker
from src.application.knowledge_gap import knowledge_gap
from src.routing.normalization import normalize_query
from src.routing.technical import TechnicalRouter
from src.safety.profanity import ProfanityDetector, RuleProfanityDetector


PROFANITY_MESSAGE = "В вашем сообщении используется нецензурная лексика. Пожалуйста, переформулируйте вопрос без неё, и я постараюсь помочь."
CLARIFICATION_MESSAGE = "Уточните, пожалуйста, что именно не работает и на каком этапе возникает проблема?"
OPERATOR_MESSAGE = "Недостаточно надёжных сведений для ответа. Передаю обращение оператору поддержки."


@dataclass(frozen=True)
class QueryPreprocessor:
    detector: ProfanityDetector | None = None

    def process(self, query: str) -> dict:
        started = perf_counter()
        detector = self.detector or RuleProfanityDetector()
        result = detector.detect(query)
        moderation = {
            "contains_profanity": result.detected,
            "backend": detector.backend,
            "probability": result.probability,
            "threshold": result.threshold,
            "latency_ms": (perf_counter() - started) * 1000,
        }
        return {"original_query": query, "moderation": moderation, "normalized_query": None if result.detected else normalize_query(query)}


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
        scores = [float(next((item[key] for key in ("reranker_score", "rrf_score", "score", "raw_score") if item.get(key) is not None), 0.0)) for item in candidates]
        official = [item for item in candidates if item.get("authority") == "official"]
        tickets = [item for item in candidates if item.get("source_type") == "support_ticket"]
        bm25_ids = {item.get("chunk_id") for item in trace.get("official_bm25", [])}
        bm25_scores = [float(item.get("raw_score", item.get("score", 0.0)) or 0.0) for item in trace.get("official_bm25", [])]
        # ``official_dense`` is the bounded authoritative collection: official
        # KB/manual chunks plus the curated support taxonomy.  Its cosine scores
        # share one scale even though taxonomy has authority="taxonomy" rather
        # than authority="official".
        dense_candidates = list(trace.get("official_dense", []))
        dense_ids = {item.get("chunk_id") for item in dense_candidates}
        overlap = len(bm25_ids & dense_ids)
        agreement = overlap / max(min(len(bm25_ids), len(dense_ids)), 1) if dense_ids else 0.0
        dense_scores = [float(item.get("raw_score", item.get("score", 0.0)) or 0.0) for item in dense_candidates]
        # CONFIDENCE_MIN_OFFICIAL_SCORE is calibrated on Qwen cosine scores.  A
        # compacted candidate may be a BM25 rescue item, whose raw score is on a
        # different scale and must never be compared to that threshold.
        official_confidence_score = dense_scores[0] if dense_scores else None
        return {
            "top_score": scores[0] if scores else 0.0,
            "bm25_top_score": bm25_scores[0] if bm25_scores else None,
            "dense_top_score": dense_scores[0] if dense_scores else None,
            "official_confidence_score": official_confidence_score,
            "official_confidence_score_method": "dense_cosine" if dense_scores else None,
            "dense_top1_top2_gap": dense_scores[0] - dense_scores[1] if len(dense_scores) > 1 else (dense_scores[0] if dense_scores else None),
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
        confidence_score = features.get("official_confidence_score")
        if official and confidence_score is not None and confidence_score < self.min_official_score:
            return "ESCALATE_TO_OPERATOR", "official_dense_score_below_threshold"
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
                 evidence_max_per_document: int = 2, clarification_policy: ClarificationPolicy | None = None,
                 evidence_sufficiency: EvidenceSufficiencyChecker | None = None):
        self.retriever = retriever
        self.preprocessor = preprocessor or QueryPreprocessor()
        self.router = router or SupportRouter()
        self.context = context or ContextAnalyzer()
        self.reranker = reranker or NoopReranker()
        self.rerank_enabled = rerank_enabled
        self.generator = generator or EvidenceGenerator()
        self.confidence = confidence or ConfidenceEvaluator()
        self.clarification_policy = clarification_policy or ClarificationPolicy()
        self.evidence_sufficiency = evidence_sufficiency or EvidenceSufficiencyChecker()
        self.final_top_k = final_top_k
        self.rerank_top_n = rerank_top_n
        self.evidence_max_per_document = evidence_max_per_document

    def ask(self, query: str) -> dict:
        started = perf_counter()
        prepared = self.preprocessor.process(query)
        base = {"original_query": query, "normalized_query": prepared["normalized_query"], "sources": []}
        if prepared["moderation"]["contains_profanity"]:
            return {**base, "status": "REFUSE_PROFANITY", "route": None, "answer": PROFANITY_MESSAGE,
                    "diagnostics": {"profanity_backend": prepared["moderation"]["backend"], "profanity_detected": True, "profanity_probability": prepared["moderation"]["probability"], "profanity_threshold": prepared["moderation"]["threshold"], "profanity_latency_ms": prepared["moderation"]["latency_ms"], "dense_available": False, "fallback_used": False, "retrieval_mode": "NONE", "dense_candidates": 0, "bm25_candidates": 0, "retrieved_count": 0, "reranker_used": False,
                                    "retrieval_strategy": "NONE", "dense_primary_used": False, "bm25_rescue_used": False, "bm25_fallback_used": False,
                                    "clarification_policy_triggered": False, "clarification_reason": "NONE",
                                    "timings_ms": {"total": (perf_counter() - started) * 1000}}}
        normalized = prepared["normalized_query"]
        assert normalized is not None
        if self.context.needs_clarification(normalized):
            return {**base, "status": "NEEDS_CLARIFICATION", "route": None, "answer": CLARIFICATION_MESSAGE,
                    "diagnostics": {"profanity_backend": prepared["moderation"]["backend"], "profanity_detected": False, "profanity_probability": prepared["moderation"]["probability"], "profanity_threshold": prepared["moderation"]["threshold"], "profanity_latency_ms": prepared["moderation"]["latency_ms"], "dense_available": False, "fallback_used": False, "retrieval_mode": "NONE", "dense_candidates": 0, "bm25_candidates": 0, "retrieved_count": 0, "reranker_used": False,
                                    "retrieval_strategy": "NONE", "dense_primary_used": False, "bm25_rescue_used": False, "bm25_fallback_used": False,
                                    "clarification_policy_triggered": False, "clarification_reason": "NONE",
                                    "timings_ms": {"total": (perf_counter() - started) * 1000}}}
        route = self.router.classify(normalized)
        clarification = self.clarification_policy.evaluate(
            normalized, route["route"], ConfidenceSignals(),
        )
        if clarification.triggered:
            return {**base, "status": "NEEDS_CLARIFICATION", "route": route["route"], "answer": CLARIFICATION_MESSAGE,
                    "diagnostics": {"profanity_backend": prepared["moderation"]["backend"], "profanity_detected": False, "profanity_probability": prepared["moderation"]["probability"], "profanity_threshold": prepared["moderation"]["threshold"], "profanity_latency_ms": prepared["moderation"]["latency_ms"], "dense_available": False, "fallback_used": False, "retrieval_mode": "NONE", "dense_candidates": 0, "bm25_candidates": 0, "retrieved_count": 0, "reranker_used": False,
                                    "retrieval_strategy": "NONE", "dense_primary_used": False, "bm25_rescue_used": False, "bm25_fallback_used": False,
                                    "clarification_policy_triggered": True, "clarification_reason": clarification.reason,
                                    "timings_ms": {"total": (perf_counter() - started) * 1000}}}
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
        sufficiency = self.evidence_sufficiency.evaluate(normalized, candidates)
        if status == "ANSWER" and not sufficiency.sufficient:
            status, reason = "ESCALATE_TO_OPERATOR", f"evidence_insufficient:{sufficiency.reason}"
        generation_started = perf_counter()
        generated = self.generator.answer(candidates) if status == "ANSWER" else {"answer": OPERATOR_MESSAGE, "used_evidence": False}
        sources = [{key: item.get(key) for key in ("chunk_id", "document_id", "source_type", "authority", "source_path", "title", "section", "page_start", "page_end", "retrieval_method", "raw_score", "rrf_score", "metadata")} for item in candidates]
        timings = dict(trace.get("timing", {}))
        timings["generation_ms"] = (perf_counter() - generation_started) * 1000
        timings["total"] = (perf_counter() - started) * 1000
        gap = knowledge_gap(query=query, normalized_query=normalized, status=status, reason=reason,
                            trace=trace, features=features, candidates=candidates)
        return {**base, "status": status, "route": route["route"], "answer": generated["answer"], "sources": sources,
                "diagnostics": {"profanity_backend": prepared["moderation"]["backend"], "profanity_detected": False, "profanity_probability": prepared["moderation"]["probability"], "profanity_threshold": prepared["moderation"]["threshold"], "profanity_latency_ms": prepared["moderation"]["latency_ms"], "dense_available": trace.get("dense_available", False), "fallback_used": trace.get("fallback_used", False),
                                "retrieval_mode": trace.get("retrieval_mode", "BM25_ONLY"), "dense_candidates": trace.get("dense_candidates", 0),
                                "bm25_candidates": trace.get("bm25_candidates", 0), "hybrid_candidates": trace.get("hybrid_candidates", 0),
                                "final_candidates": trace.get("final_candidates", len(candidates)),
                                "retrieval_strategy": trace.get("retrieval_strategy", "BM25_ONLY"),
                                "dense_primary_used": trace.get("dense_primary_used", False),
                                "bm25_rescue_used": trace.get("bm25_rescue_used", False),
                                "bm25_fallback_used": trace.get("bm25_fallback_used", False),
                                "clarification_policy_triggered": False, "clarification_reason": "NONE",
                                "retrieved_count": len(candidates), "reranker_enabled": self.rerank_enabled, "reranker_available": reranker_available,
                                "reranker_used": reranker_used, "reranker_latency_ms": float(getattr(self.reranker, "last_latency_ms", 0.0)),
                                "reranker_candidates": min(len(trace["results"]), self.rerank_top_n) if self.rerank_enabled else 0,
                                "confidence": features, "confidence_reason": reason, "knowledge_gap": gap,
                                "evidence_sufficiency": {"enabled": self.evidence_sufficiency.enabled, "sufficient": sufficiency.sufficient,
                                                         "reason": sufficiency.reason, "required_terms": list(sufficiency.required_terms),
                                                         "missing_terms": list(sufficiency.missing_terms)},
                                "context": tagged_context(candidates),
                                "timings_ms": timings}}
