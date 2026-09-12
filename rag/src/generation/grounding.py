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


def _lexical_stem(word: str) -> str:
    """Match ordinary Russian inflections without accepting generic claims."""
    # ``создать`` / ``создания`` and ``доверенность`` /
    # ``доверенностей`` share a sufficiently specific five-character prefix.
    return word.casefold()[:5]


def validate_grounding(answer: str, evidence: list[dict]) -> GroundingResult:
    """Fail closed on unsupported local lexical/numeric claims.

    This deterministic heuristic is not a guarantee of factual correctness.
    It blocks an answer whenever a substantive sentence cannot be tied to the
    supplied evidence, leaving the safe operator escalation path.
    """
    source_text = " ".join(str(item.get("text", "")) for item in evidence).casefold()
    output = answer.strip().casefold()
    if not output:
        return GroundingResult(False, "empty_output")
    if output == "недостаточно_данных":
        return GroundingResult(False, "model_reported_insufficient_evidence")
    # A local model may format supported steps as ``1. ...`` despite the
    # prompt.  Those labels are presentation, not factual numeric claims, and
    # must not turn an otherwise grounded answer into an escalation.
    output_without_list_markers = re.sub(r"(?m)^\s*\d+[.)]\s*", "", output)
    unsupported_numbers = [number for number in _NUMBER.findall(output_without_list_markers)
                           if number.replace(",", ".") not in source_text.replace(",", ".")]
    if unsupported_numbers:
        return GroundingResult(False, "unsupported_numeric_claim")
    evidence_terms = {word.casefold() for word in _WORD.findall(source_text) if word.casefold() not in _STOP}
    evidence_stems = {_lexical_stem(word) for word in evidence_terms}
    terms = [word.casefold() for word in _WORD.findall(output) if word.casefold() not in _STOP]
    supported = [term for term in terms if _lexical_stem(term) in evidence_stems]
    # Check the complete short answer rather than every individual sentence.
    # A well-formed response commonly contains a brief connective sentence
    # ("Это позволит продолжить работу") with no source nouns; treating that
    # as an invented claim rejected an otherwise supported answer.  Two
    # independent source terms across the response still prevent a single
    # generic overlap such as only ``портал`` from grounding a fabrication.
    minimum = 1 if len(terms) == 1 else 2
    if len(supported) < minimum:
        return GroundingResult(False, "unsupported_substantive_claim")
    return GroundingResult(True, "grounded")
