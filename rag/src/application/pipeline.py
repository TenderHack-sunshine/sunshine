from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from src.generation.generator import EvidenceGenerator
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

    def __init__(self, min_sources: int = 1):
        self.min_sources = min_sources

    def decide(self, route: str, candidates: list[dict]) -> tuple[str, str | None]:
        if len(candidates) < self.min_sources:
            return "ESCALATE_TO_OPERATOR", "no_relevant_evidence"
        official = any(item.get("authority") == "official" for item in candidates)
        ticket = any(item.get("source_type") == "support_ticket" for item in candidates)
        if route == "L3" and not (official or ticket):
            return "ESCALATE_TO_OPERATOR", "no_support_evidence"
        return "ANSWER", None


class RAGService:
    """Orchestrates guards, routing, swappable retrieval/reranking and evidence output."""

    def __init__(self, retriever, *, preprocessor: QueryPreprocessor | None = None, router: SupportRouter | None = None,
                 context: ContextAnalyzer | None = None, reranker=None, rerank_enabled: bool = False,
                 generator=None, confidence: ConfidenceEvaluator | None = None, final_top_k: int = 5):
        self.retriever = retriever
        self.preprocessor = preprocessor or QueryPreprocessor()
        self.router = router or SupportRouter()
        self.context = context or ContextAnalyzer()
        self.reranker = reranker or NoopReranker()
        self.rerank_enabled = rerank_enabled
        self.generator = generator or EvidenceGenerator()
        self.confidence = confidence or ConfidenceEvaluator()
        self.final_top_k = final_top_k

    def ask(self, query: str) -> dict:
        started = perf_counter()
        prepared = self.preprocessor.process(query)
        base = {"original_query": query, "normalized_query": prepared["normalized_query"], "sources": []}
        if prepared["moderation"]["contains_profanity"]:
            return {**base, "status": "REJECTED_PROFANITY", "route": None, "answer": PROFANITY_MESSAGE,
                    "diagnostics": {"dense_available": False, "fallback_used": False, "retrieved_count": 0, "reranker_used": False,
                                    "timings_ms": {"total": (perf_counter() - started) * 1000}}}
        normalized = prepared["normalized_query"]
        assert normalized is not None
        if self.context.needs_clarification(normalized):
            return {**base, "status": "NEEDS_CLARIFICATION", "route": None, "answer": CLARIFICATION_MESSAGE,
                    "diagnostics": {"dense_available": False, "fallback_used": False, "retrieved_count": 0, "reranker_used": False,
                                    "timings_ms": {"total": (perf_counter() - started) * 1000}}}
        route = self.router.classify(normalized)
        trace = self.retriever.retrieve_with_trace(normalized, technical=route["technical"])
        candidates = trace["results"]
        reranker_used = False
        if self.rerank_enabled:
            try:
                candidates = self.reranker.rerank(normalized, candidates[:10], self.final_top_k)
                reranker_used = True
            except Exception as error:
                trace["reranker_error"] = str(error)
                candidates = candidates[:self.final_top_k]
        else:
            candidates = candidates[:self.final_top_k]
        status, reason = self.confidence.decide(route["route"], candidates)
        generated = self.generator.answer(candidates) if status == "ANSWER" else {"answer": OPERATOR_MESSAGE, "used_evidence": False}
        sources = [{key: item.get(key) for key in ("chunk_id", "document_id", "source_type", "authority", "source_path", "title", "section", "page_start", "page_end", "retrieval_method", "raw_score", "rrf_score", "metadata")} for item in candidates]
        timings = dict(trace.get("timing", {}))
        timings["total"] = (perf_counter() - started) * 1000
        return {**base, "status": status, "route": route["route"], "answer": generated["answer"], "sources": sources,
                "diagnostics": {"dense_available": trace.get("dense_available", False), "fallback_used": trace.get("fallback_used", False),
                                "retrieved_count": len(candidates), "reranker_used": reranker_used, "confidence_reason": reason,
                                "timings_ms": timings}}
