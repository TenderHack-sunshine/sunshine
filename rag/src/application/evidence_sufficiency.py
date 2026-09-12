"""Lightweight claim-to-evidence guard for extractive RAG answers.

It is deliberately opt-in until a human-labelled calibration set is reviewed.
The check is not a semantic judge: it only rejects clear contradictions between
the shape of a request (navigation or a named specific fact) and the returned
extractive evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


_TOKEN = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
_STOP = {
    "а", "без", "в", "во", "где", "для", "и", "из", "как", "какая", "какие", "какой", "ли", "на", "не", "о", "об",
    "по", "при", "с", "со", "у", "что", "это", "за", "мне", "нужен", "нужна", "нужно", "пожалуйста", "точный",
}
_FACT_HEADS = {"сколько", "какая", "какие", "какой", "точный", "размер", "сумма", "срок"}
_NAVIGATION_HEADS = {"где", "куда", "раздел", "меню", "найти", "посмотреть"}
_NAVIGATION_EVIDENCE = {"раздел", "меню", "вкладк", "перейт", "нажат", "открыт", "профил", "кабинет", "выбрат", "загруз"}


@dataclass(frozen=True)
class EvidenceSufficiencyResult:
    sufficient: bool
    reason: str
    required_terms: tuple[str, ...] = ()
    missing_terms: tuple[str, ...] = ()


def _stem(token: str) -> str:
    """Small, deterministic Russian-friendly normalisation; not a lemmatiser."""
    token = token.lower().replace("ё", "е")
    for suffix in ("иями", "ями", "ами", "ого", "ему", "ому", "иях", "иях", "иях", "иях", "ать", "ять", "ить", "еть", "ться", "ется", "ится", "ов", "ев", "ей", "ам", "ям", "ах", "ях", "ы", "и", "а", "я", "у", "ю", "е", "о"):
        if len(token) - len(suffix) >= 4 and token.endswith(suffix):
            return token[:-len(suffix)]
    return token


def _terms(text: str) -> set[str]:
    return {_stem(token) for token in _TOKEN.findall(text) if token not in _STOP}


class EvidenceSufficiencyChecker:
    """Reject only clearly unsupported navigation / specific-fact requests."""

    def __init__(self, *, enabled: bool = False):
        self.enabled = enabled

    def evaluate(self, query: str, candidates: list[dict]) -> EvidenceSufficiencyResult:
        if not self.enabled:
            return EvidenceSufficiencyResult(True, "DISABLED")
        if not candidates:
            return EvidenceSufficiencyResult(False, "NO_EVIDENCE")
        query_tokens = {_stem(token) for token in _TOKEN.findall(query.lower())}
        evidence_terms = _terms(candidates[0].get("text", ""))
        if query_tokens & {_stem(head) for head in _NAVIGATION_HEADS}:
            has_navigation = any(any(term.startswith(marker) for term in evidence_terms) for marker in _NAVIGATION_EVIDENCE)
            if not has_navigation:
                return EvidenceSufficiencyResult(False, "NAVIGATION_NOT_EXPLICIT")
        if query_tokens & {_stem(head) for head in _FACT_HEADS}:
            required = tuple(sorted(term for term in _terms(query) if len(term) >= 4 and term not in {_stem(head) for head in _FACT_HEADS}))
            missing = tuple(term for term in required if term not in evidence_terms)
            if missing:
                return EvidenceSufficiencyResult(False, "REQUESTED_FACT_NOT_EXPLICIT", required, missing)
        return EvidenceSufficiencyResult(True, "SUPPORTED_BY_EXTRACTIVE_EVIDENCE")
