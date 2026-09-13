"""Clarification decisions derived from generic IntentFrame missing slots."""
from __future__ import annotations

from dataclasses import dataclass

from src.routing.intent import IntentFrame


@dataclass(frozen=True)
class ConfidenceSignals:
    top_score: float = 0.0
    retrieval_agreement: float = 0.0
    official_candidates: int = 0


@dataclass(frozen=True)
class ClarificationDecision:
    triggered: bool
    reason: str = "NONE"
    missing_slots: tuple[str, ...] = ()


class ClarificationPolicy:
    """Ask only for slots required by the recognised generic intent."""

    def __init__(self, *, enabled: bool = True, short_failure_max_tokens: int = 3,
                 broad_policy_max_tokens: int = 4):
        if short_failure_max_tokens < 1 or broad_policy_max_tokens < 1:
            raise ValueError("Clarification-policy token limits must be positive")
        self.enabled = enabled

    def evaluate(self, frame: IntentFrame, route: str | None = None,
                 confidence: ConfidenceSignals | None = None) -> ClarificationDecision:
        del route, confidence
        if not self.enabled or frame.intent == "human_request":
            return ClarificationDecision(False)
        if frame.missing_slots:
            return ClarificationDecision(True, "MISSING_REQUIRED_SLOTS", frame.missing_slots)
        return ClarificationDecision(False)


def clarification_question(frame: IntentFrame) -> str:
    slots = set(frame.missing_slots)
    if frame.intent == "troubleshooting" and ({"object", "error_text_or_stage", "symptom"} & slots):
        return "Укажите, при каком действии возникла проблема, что вы подписываете или где авторизуетесь, а также точный текст или код ошибки и этап её появления."
    if {"error_text_or_stage", "symptom"} & slots:
        return "Укажите точный текст или код ошибки и этап, на котором она возникает."
    if "object" in slots or "object_or_goal" in slots or "subject" in slots:
        return "Уточните, с каким объектом Портала вы работаете и что хотите сделать."
    if "action" in slots:
        return "Уточните требуемое действие: создать, добавить, найти, изменить, подписать, отправить, исправить или проверить."
    return "Уточните, пожалуйста, объект, действие и этап, на котором возник вопрос."
