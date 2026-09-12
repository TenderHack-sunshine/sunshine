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
# "почему" asks the system to substantiate a concrete cause.  Without this
# guard, a sparse match on a generic word such as "портал" could turn an
# unrelated question into an apparently confident answer.
_FACT_HEADS = {"сколько", "какая", "какие", "какой", "точный", "размер", "сумма", "срок", "почему"}
_NAVIGATION_HEADS = {"где", "куда", "раздел", "меню", "найти", "посмотреть"}
_NAVIGATION_EVIDENCE = {"раздел", "меню", "вкладк", "перейт", "нажат", "открыт", "профил", "кабинет", "выбрат", "загруз"}
_EXACT_FACT_TERMS = {"комисси", "штраф", "сумм", "процент", "размер"}
_NUMBER_WORDS = {"один", "одна", "два", "две", "три", "трех", "четыр", "пят", "шест", "сем", "восем", "девят", "десят", "сто"}
_CONTACT_TERMS = {"контакт", "телефон", "почт", "связ", "обращен", "поддержк"}
_CONSEQUENCE_TERMS = {"последств", "ответственност"}
_CONTACT_QUERY_STOP = {"как", "связ", "моим", "персональн", "портал", "поставщик"}
_WHY_QUERY_STOP = {"\u043f\u043e\u0447\u0435\u043c", "\u043f\u043e\u0440\u0442\u0430\u043b", "\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u0442"}


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


def _has_explicit_number(text: str, fact_terms: set[str]) -> bool:
    """Require a number in the same sentence as the requested fact.

    Figure labels such as ``Рисунок 1`` must not count as an amount, deadline,
    or penalty value.
    """
    for sentence in re.split(r"[.!?\n]+", text):
        terms = _terms(sentence)
        if fact_terms and not any(term in terms for term in fact_terms):
            continue
        # Captions are layout artefacts, not a stated amount, period, or rate.
        # Remove them before looking for a numeric value in the same claim.
        claim = re.sub(
            r"(?:\u0440\u0438\u0441\u0443\u043d\u043e\u043a|\u0442\u0430\u0431\u043b\u0438\u0446\u0430)\s*\d+(?:\s*\([^)]*\))?",
            "",
            sentence,
            flags=re.IGNORECASE,
        )
        if re.search(r"\d", claim) or _terms(claim) & _NUMBER_WORDS:
            return True
    return False


def _supported_terms(query_terms: set[str], evidence_terms: set[str]) -> set[str]:
    """Match the small stems conservatively without pretending to lemmatise."""
    return {
        query_term for query_term in query_terms
        if any(query_term.startswith(evidence_term) or evidence_term.startswith(query_term) for evidence_term in evidence_terms)
    }


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
        # Evaluate precisely the complete context that is allowed to reach the
        # generator, not merely retrieval rank #1.
        evidence_text = "\n\n".join(str(candidate.get("text", "")) for candidate in candidates)
        evidence_terms = _terms(evidence_text)
        if query_tokens & {_stem(head) for head in _NAVIGATION_HEADS}:
            has_navigation = any(any(term.startswith(marker) for term in evidence_terms) for marker in _NAVIGATION_EVIDENCE)
            if not has_navigation:
                return EvidenceSufficiencyResult(False, "NAVIGATION_NOT_EXPLICIT")
        if any(token.startswith("\u0441\u0432\u044f\u0437") for token in query_tokens):
            if not any(term.startswith(marker) for marker in _CONTACT_TERMS for term in evidence_terms):
                return EvidenceSufficiencyResult(False, "CONTACT_PATH_NOT_EXPLICIT")
            contact_targets = {
                term for term in query_tokens if len(term) >= 5 and term not in _CONTACT_QUERY_STOP
            }
            if contact_targets and not contact_targets & evidence_terms:
                return EvidenceSufficiencyResult(False, "CONTACT_TARGET_NOT_EXPLICIT", tuple(sorted(contact_targets)), tuple(sorted(contact_targets)))
        asks_about_consequences = any(
            token.startswith("\u043f\u043e\u0441\u043b\u0435\u0434\u0441\u0442\u0432")
            or token.startswith("\u043e\u0442\u0432\u0435\u0442\u0441\u0442\u0432")
            or token.startswith("\u044e\u0440\u0438\u0434\u0438\u0447")
            for token in query_tokens
        )
        has_consequence_evidence = any(
            term.startswith("\u043f\u043e\u0441\u043b\u0435\u0434\u0441\u0442\u0432")
            or term.startswith("\u043e\u0442\u0432\u0435\u0442\u0441\u0442\u0432")
            for term in evidence_terms
        )
        if asks_about_consequences and not has_consequence_evidence:
            return EvidenceSufficiencyResult(False, "CONSEQUENCE_NOT_EXPLICIT")
        if asks_about_consequences:
            # A how-to manual can describe an upload button but cannot, by
            # itself, establish legal force or a sanction.  A historical ticket
            # is never normative evidence either.  Until a dedicated
            # normative-source type is added, only the official KB (or an
            # explicitly marked normative record) can support this answer.
            normative_candidates = [
                candidate for candidate in candidates
                if candidate.get("source_type") == "official_kb"
                or bool((candidate.get("metadata") or {}).get("normative_source"))
            ]
            normative_text = "\n".join(str(candidate.get("text", "")) for candidate in normative_candidates)
            normative_terms = _terms(normative_text)
            if not normative_candidates:
                return EvidenceSufficiencyResult(False, "CONSEQUENCE_REQUIRES_NORMATIVE_EVIDENCE")
            if not any(
                term.startswith("\u043f\u043e\u0441\u043b\u0435\u0434\u0441\u0442\u0432")
                or term.startswith("\u043e\u0442\u0432\u0435\u0442\u0441\u0442\u0432")
                or term.startswith("\u044e\u0440\u0438\u0434\u0438\u0447")
                for term in normative_terms
            ):
                return EvidenceSufficiencyResult(False, "CONSEQUENCE_NOT_IN_NORMATIVE_EVIDENCE")
        if any(term.startswith("\u043f\u043e\u0447\u0435\u043c") for term in query_tokens):
            causal_subject = {
                term for term in query_tokens if len(term) >= 5 and term not in _WHY_QUERY_STOP
            }
            supported = _supported_terms(causal_subject, evidence_terms)
            # A causal answer needs more than one generic topical overlap when
            # the query names several subject terms.  This rejects a semantically
            # adjacent article from being presented as an explanation.
            minimum_supported = min(2, len(causal_subject))
            if len(supported) < minimum_supported:
                missing = tuple(sorted(causal_subject - supported))
                return EvidenceSufficiencyResult(False, "REQUESTED_FACT_NOT_EXPLICIT", tuple(sorted(causal_subject)), missing)
        exact_terms = query_tokens & _EXACT_FACT_TERMS
        numeric_question = bool(exact_terms) or "\u0441\u043a\u043e\u043b\u044c\u043a\u043e" in query_tokens or ("\u0441\u0440\u043e\u043a" in query_tokens and "\u043c\u0430\u043a\u0441\u0438\u043c\u0430\u043b\u044c\u043d" in query_tokens)
        if exact_terms or numeric_question:
            required = tuple(sorted(exact_terms))
            missing = tuple(term for term in required if term not in evidence_terms)
            if missing:
                return EvidenceSufficiencyResult(False, "REQUESTED_FACT_NOT_EXPLICIT", required, missing)
            numeric_targets = exact_terms or ({"\u0441\u0440\u043e\u043a"} if "\u0441\u0440\u043e\u043a" in query_tokens else set())
            if numeric_question and not _has_explicit_number(evidence_text, numeric_targets):
                return EvidenceSufficiencyResult(False, "REQUESTED_NUMBER_NOT_EXPLICIT", required, ("number",))
        return EvidenceSufficiencyResult(True, "SUPPORTED_BY_EXTRACTIVE_EVIDENCE")
