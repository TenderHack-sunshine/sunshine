from __future__ import annotations

from src.generation.generator import EvidenceGenerator
from src.moderation.profanity import detect_profanity
from src.routing.normalization import normalize_query
from src.routing.technical import TechnicalRouter


def answer_question(question: str, retriever, router=None, generator: EvidenceGenerator | None = None) -> dict:
    moderation = detect_profanity(question)
    if moderation["contains_profanity"]:
        return {
            "moderation": moderation, "normalized_query": None, "route": None, "evidence": [], "used_evidence": False,
            "answer": "Запрос отклонён из-за недопустимой лексики. Переформулируйте его нейтрально.",
        }
    normalized = normalize_query(question)
    taxonomy_route = router.classify(normalized) if router else {"topic": None, "subtopic": None, "confidence": 0.0}
    technical_route = TechnicalRouter().classify(normalized)
    try:
        evidence = retriever.search(normalized, technical=technical_route["technical"])
    except TypeError:
        evidence = retriever.search(normalized)
    answer = (generator or EvidenceGenerator()).answer(evidence)
    return {
        "moderation": moderation, "normalized_query": normalized,
        "route": {"taxonomy": taxonomy_route, "technical": technical_route}, "evidence": evidence, **answer,
    }
