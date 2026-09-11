from __future__ import annotations

from time import perf_counter

from src.generation.generator import EvidenceGenerator
from src.moderation.profanity import detect_profanity
from src.routing.normalization import normalize_query
from src.routing.technical import TechnicalRouter


def _empty_trace(preprocessing_ms: float) -> dict:
    return {
        "dense_available": False,
        "fallback_used": False,
        "results": [],
        "timing": {
            "preprocessing_ms": preprocessing_ms,
            "query_embedding_ms": 0.0,
            "dense_search_ms": 0.0,
            "bm25_ms": 0.0,
            "fusion_ms": 0.0,
            "total_retrieval_ms": 0.0,
        },
    }


def answer_question(question: str, retriever, router=None, generator: EvidenceGenerator | None = None) -> dict:
    """Run moderation before retrieval and retain a development retrieval trace."""
    started = perf_counter()
    moderation = detect_profanity(question)
    if moderation["contains_profanity"]:
        return {
            "moderation": moderation,
            "normalized_query": None,
            "route": None,
            "evidence": [],
            "used_evidence": False,
            "answer": "Запрос отклонён из-за недопустимой лексики. Переформулируйте его нейтрально.",
            "retrieval": _empty_trace((perf_counter() - started) * 1000),
        }

    normalized = normalize_query(question)
    taxonomy_route = router.classify(normalized) if router else {"topic": None, "subtopic": None, "confidence": 0.0}
    technical_route = TechnicalRouter().classify(normalized)
    preprocessing_ms = (perf_counter() - started) * 1000

    if hasattr(retriever, "retrieve_with_trace"):
        retrieval = retriever.retrieve_with_trace(normalized, technical=technical_route["technical"])
        evidence = retrieval["results"]
    else:
        try:
            evidence = retriever.search(normalized, technical=technical_route["technical"])
        except TypeError:
            evidence = retriever.search(normalized)
        retrieval = _empty_trace(preprocessing_ms)
        retrieval["results"] = evidence
    retrieval.setdefault("timing", {})["preprocessing_ms"] = preprocessing_ms

    answer = (generator or EvidenceGenerator()).answer(evidence)
    return {
        "moderation": moderation,
        "normalized_query": normalized,
        "route": {"taxonomy": taxonomy_route, "technical": technical_route},
        "evidence": evidence,
        "retrieval": retrieval,
        **answer,
    }
