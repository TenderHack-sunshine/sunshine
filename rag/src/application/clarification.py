"""Deterministic query-ambiguity policy, independent from retrieval confidence."""
from __future__ import annotations

from dataclasses import dataclass

from src.routing.normalization import normalize_query


@dataclass(frozen=True)
class ConfidenceSignals:
    """Evidence confidence is accepted for diagnostics/future policy, not conflated with intent ambiguity."""

    top_score: float = 0.0
    retrieval_agreement: float = 0.0
    official_candidates: int = 0


@dataclass(frozen=True)
class ClarificationDecision:
    triggered: bool
    reason: str = "NONE"


class ClarificationPolicy:
    """Narrow, configurable clarification rules for underspecified user intent."""

    _failure_prefixes = ("не могу", "не получается", "не работает", "не открыва", "не груз", "не подписыва", "ошибка", "сбой", "завис")
    _broad_policy_heads = {"правила", "регламент", "условия"}
    _underspecified_lifecycle_actions = {"исправить", "отменить", "изменить", "отозвать"}

    def __init__(self, *, enabled: bool = True, short_failure_max_tokens: int = 3, broad_policy_max_tokens: int = 4):
        if short_failure_max_tokens < 1 or broad_policy_max_tokens < 1:
            raise ValueError("Clarification-policy token limits must be positive")
        self.enabled = enabled
        self.short_failure_max_tokens = short_failure_max_tokens
        self.broad_policy_max_tokens = broad_policy_max_tokens

    def evaluate(self, query: str, route: str, confidence: ConfidenceSignals | None = None) -> ClarificationDecision:
        """Return only query-intent ambiguity; evidence strength remains a separate decision."""
        del confidence  # Deliberately do not let a high score override ambiguous intent.
        if not self.enabled:
            return ClarificationDecision(False)
        normalized = normalize_query(query)
        tokens = normalized.split()
        compact = " ".join(tokens)
        if len(tokens) <= self.short_failure_max_tokens and any(compact.startswith(prefix) for prefix in self._failure_prefixes):
            return ClarificationDecision(True, "SHORT_FAILURE_QUERY")
        if route == "L2" and len(tokens) <= self.broad_policy_max_tokens and tokens and tokens[0] in self._broad_policy_heads:
            return ClarificationDecision(True, "BROAD_POLICY_QUERY")
        # A lifecycle action without a named document type or workflow cannot
        # safely select one of several portal procedures.
        if len(tokens) <= 7 and any(action in tokens for action in self._underspecified_lifecycle_actions) and "закупку" in tokens:
            return ClarificationDecision(True, "UNDERSPECIFIED_LIFECYCLE_ACTION")
        return ClarificationDecision(False)
