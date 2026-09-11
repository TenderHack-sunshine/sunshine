from __future__ import annotations

from src.generation.generator import EvidenceGenerator
from src.moderation.profanity import detect_profanity


def answer_question(question: str, retriever, router=None, generator: EvidenceGenerator | None = None) -> dict:
    moderation = detect_profanity(question)
    route = router.classify(question) if router else {"topic": None, "subtopic": None, "confidence": 0.0}
    evidence = retriever.search(question)
    answer = (generator or EvidenceGenerator()).answer(evidence)
    return {"moderation": moderation, "route": route, "evidence": evidence, **answer}
