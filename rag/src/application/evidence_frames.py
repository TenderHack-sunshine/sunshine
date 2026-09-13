"""Evidence metadata used to prevent object/action mismatched answers."""
from __future__ import annotations

from dataclasses import dataclass

from src.routing.intent import DomainLexicon, IntentFrame, action_from_text


@dataclass(frozen=True)
class EvidenceFrame:
    objects: tuple[str, ...]
    actions: tuple[str, ...]
    answer_types: tuple[str, ...]
    roles: tuple[str, ...]
    error_codes: tuple[str, ...]
    source_authority: str


def frame_evidence(candidate: dict, lexicon: DomainLexicon) -> EvidenceFrame:
    text = " ".join(str(candidate.get(key, "")) for key in ("title", "section", "text"))
    obj = lexicon.match(text)
    action = action_from_text(text)
    answer_types = []
    lowered = text.casefold()
    if "что такое" in lowered or "определ" in lowered:
        answer_types.append("definition")
    if action:
        answer_types.append("how_to")
    if any(marker in lowered for marker in ("ошиб", "сбой", "не работа", "не открыва")):
        answer_types.append("troubleshooting")
    return EvidenceFrame(objects=(obj,) if obj else (), actions=(action,) if action else (),
                         answer_types=tuple(answer_types), roles=(str(candidate["role"]),) if candidate.get("role") else (),
                         error_codes=(), source_authority=str(candidate.get("authority", "unknown")))


def compatibility(intent: IntentFrame, evidence: EvidenceFrame) -> tuple[bool, str]:
    if evidence.source_authority == "case_history" and intent.intent != "troubleshooting":
        return False, "CASE_HISTORY_NOT_ALLOWED_FOR_INTENT"
    if intent.object and evidence.objects and not any(_same_object(intent.object, item) for item in evidence.objects):
        return False, "OBJECT_MISMATCH"
    if intent.action and intent.intent in {"how_to", "navigation"} and not evidence.actions:
        return False, "ACTION_NOT_EVIDENCED"
    if intent.action and evidence.actions and intent.action not in evidence.actions:
        return False, "ACTION_MISMATCH"
    if intent.intent == "definition" and evidence.answer_types and "definition" not in evidence.answer_types:
        return False, "ANSWER_TYPE_MISMATCH"
    return True, "COMPATIBLE"


def _same_object(left: str, right: str) -> bool:
    """Compare corpus-derived object labels across ordinary word forms."""
    left_terms = {term[:5] for term in left.casefold().split() if len(term) >= 4}
    right_terms = {term[:5] for term in right.casefold().split() if len(term) >= 4}
    return bool(left_terms and right_terms and left_terms & right_terms)
