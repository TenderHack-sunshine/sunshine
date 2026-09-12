"""Small conservative post-generation guard; retrieval/evidence policy stays unchanged."""
from __future__ import annotations

import re
from dataclasses import dataclass

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_WORD = re.compile(r"[а-яёa-z]{4,}", re.IGNORECASE)
_STOP = {"этого", "который", "которые", "пожалуйста", "нужно", "можно", "чтобы", "будет", "ответ", "пользователь"}


@dataclass(frozen=True)
class GroundingResult:
    grounded: bool
    reason: str


def validate_grounding(answer: str, evidence: list[dict]) -> GroundingResult:
    """Reject empty, refusal-marker, and numerically unsupported model output.

    This is intentionally a narrow fail-closed check. Evidence sufficiency remains
    the policy that decides whether an answer may be attempted in the first place.
    """
    source_text = " ".join(str(item.get("text", "")) for item in evidence).casefold()
    output = answer.strip().casefold()
    if not output:
        return GroundingResult(False, "empty_output")
    if output == "недостаточно_данных":
        return GroundingResult(False, "model_reported_insufficient_evidence")
    unsupported_numbers = [number for number in _NUMBER.findall(output) if number.replace(",", ".") not in source_text.replace(",", ".")]
    if unsupported_numbers:
        return GroundingResult(False, "unsupported_numeric_claim")
    terms = [word for word in _WORD.findall(output) if word not in _STOP]
    if terms and not any(word in source_text for word in terms):
        return GroundingResult(False, "no_lexical_evidence_overlap")
    return GroundingResult(True, "grounded")
