"""Clarify only when the current turn lacks information needed to proceed."""
from __future__ import annotations

from dataclasses import dataclass

from src.routing.normalization import normalize_query


@dataclass(frozen=True)
class ConfidenceSignals:
    top_score: float = 0.0
    retrieval_agreement: float = 0.0
    official_candidates: int = 0


@dataclass(frozen=True)
class ClarificationDecision:
    triggered: bool
    reason: str = "NONE"


class ClarificationPolicy:
    """Recognise incomplete turns independently of the portal topic.

    A clarification is for missing user context, not weak retrieval. A concrete
    request such as ``Ошибка при загрузке XML`` remains answerable; a report
    such as ``выходит ошибка`` cannot be diagnosed without the error text and
    is clarified even when it follows a relevant earlier question.
    """

    # ``normalize_query`` removes punctuation, so this deliberately excludes
    # the colon used by the API when it joins the previous topic.
    _context_marker = "уточнение к предыдущей теме"
    _vague_exact = {"работа", "ошибка", "не работает", "не получается", "не могу", "не входит"}
    _status_prefixes = ("выходит ошиб", "появилась ошиб", "та же ошиб", "снова ошиб")

    def __init__(self, *, enabled: bool = True, short_failure_max_tokens: int = 3,
                 broad_policy_max_tokens: int = 4):
        if short_failure_max_tokens < 1 or broad_policy_max_tokens < 1:
            raise ValueError("Clarification-policy token limits must be positive")
        self.enabled = enabled
        # Retained to keep existing deployment configuration valid.
        self.short_failure_max_tokens = short_failure_max_tokens
        self.broad_policy_max_tokens = broad_policy_max_tokens

    @classmethod
    def reason_for(cls, query: str) -> str | None:
        normalized = normalize_query(query)
        current = normalized
        if cls._context_marker in normalized:
            current = normalized.rsplit(cls._context_marker, 1)[1].strip()
        if current in cls._vague_exact:
            return "MISSING_SUBJECT_OR_STAGE"
        if current.startswith(cls._status_prefixes):
            return "MISSING_ERROR_DETAILS"
        # Deictic follow-ups can use the previous topic for retrieval only when
        # they explicitly ask for more explanation; "как это исправить" still
        # lacks the referent and must not select an arbitrary workflow.
        if current.startswith(("как это", "где это", "что с этим")):
            return "MISSING_REFERENT"
        if current.startswith("что делать") and len(current.split()) <= 5:
            return "MISSING_ACTION"
        # A bare subject (including МЧД) gives no operation or observed state.
        tokens = current.split()
        if len(tokens) <= 3 and current.startswith(("работа с ", "мчд", "доверенност")):
            return "MISSING_ACTION"
        return None

    def evaluate(self, query: str, route: str,
                 confidence: ConfidenceSignals | None = None) -> ClarificationDecision:
        del route, confidence
        if not self.enabled:
            return ClarificationDecision(False)
        reason = self.reason_for(query)
        return ClarificationDecision(reason is not None, reason or "NONE")
