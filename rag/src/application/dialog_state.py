"""Serializable dialog state; generators never receive a concatenated history."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from src.routing.intent import IntentFrame


@dataclass(frozen=True)
class DialogState:
    intent_frame: dict | None = None
    pending_clarification: tuple[str, ...] = ()
    clarification_count: int = 0
    resolved_query: str = ""
    handoff_offered: bool = False
    active_ticket_id: str | None = None
    topic_changed: bool = False

    @classmethod
    def from_dict(cls, value: dict | None) -> "DialogState":
        value = value if isinstance(value, dict) else {}
        return cls(intent_frame=value.get("intent_frame") if isinstance(value.get("intent_frame"), dict) else None,
                   pending_clarification=tuple(str(item) for item in value.get("pending_clarification", []) if item),
                   clarification_count=max(0, int(value.get("clarification_count", 0) or 0)),
                   resolved_query=str(value.get("resolved_query", "") or ""),
                   handoff_offered=bool(value.get("handoff_offered", False)),
                   active_ticket_id=value.get("active_ticket_id"), topic_changed=bool(value.get("topic_changed", False)))

    def to_dict(self) -> dict:
        value = asdict(self)
        value["pending_clarification"] = list(self.pending_clarification)
        return value


def update_dialog_state(previous: DialogState, frame: IntentFrame, user_text: str) -> DialogState:
    previous_frame = previous.intent_frame or {}
    previous_object = previous_frame.get("object") if isinstance(previous_frame, dict) else None
    topic_changed = bool(frame.object and previous_object and frame.object != previous_object)
    # A one-word clarification reply can supply an action while the object was
    # confirmed in the preceding turn. It does not copy arbitrary history.
    object_value = frame.object or (previous_object if previous.pending_clarification and not topic_changed else None)
    merged = {**frame.to_dict(), "object": object_value}
    missing = list(frame.missing_slots)
    if object_value and "object" in missing:
        missing.remove("object")
    merged["missing_slots"] = missing
    resolved_parts = [item for item in (merged.get("action"), merged.get("object"), merged.get("stage"), merged.get("error_text")) if item]
    resolved = " ".join(dict.fromkeys(str(item) for item in resolved_parts)) or user_text.strip()
    clarification_count = previous.clarification_count + 1 if missing else 0
    return DialogState(intent_frame=merged, pending_clarification=tuple(missing), clarification_count=clarification_count,
                       resolved_query=resolved, handoff_offered=previous.handoff_offered and bool(missing),
                       active_ticket_id=previous.active_ticket_id, topic_changed=topic_changed)
