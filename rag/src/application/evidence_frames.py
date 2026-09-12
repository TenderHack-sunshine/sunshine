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
    if intent.object and evidence.objects and intent.object not in evidence.objects:
        return False, "OBJECT_MISMATCH"
    if intent.action and evidence.actions and intent.action not in evidence.actions:
        return False, "ACTION_MISMATCH"
    if intent.intent == "definition" and evidence.answer_types and "definition" not in evidence.answer_types:
        return False, "ANSWER_TYPE_MISMATCH"
    return True, "COMPATIBLE"
