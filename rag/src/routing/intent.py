"""Local, corpus-derived intent frames for reliable dialog decisions.

The extractor contains only generic Russian action/intent grammar. Domain
objects come from local corpus and taxonomy metadata at startup, never from a
hand-written list of portal features or article identifiers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Iterable

from .normalization import normalize_query


_WORDS = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
_STOP = {
    "как", "что", "это", "эта", "этот", "или", "для", "при", "на", "в", "во", "по", "с", "и", "а",
    "мне", "нужно", "можно", "ли", "пожалуйста", "портал", "поставщиков",
}
_ACTION_CLASSES = {
    "create": ("созда", "сформир", "оформ"),
    "add_upload": ("добав", "загруз", "прикреп", "импорт"),
    "find_open": ("найт", "откр", "посмотр", "перейт"),
    "fill": ("заполн", "внест"),
    "change_replace": ("измен", "замен", "редакт"),
    "remove_revoke": ("удал", "отозв", "аннулир"),
    "sign": ("подпис", "утверд"),
    "send": ("отправ", "направ", "опублик"),
    "fix": ("исправ", "реши", "устран"),
    "check": ("провер", "узнат", "контрол"),
}
_HUMAN_REQUEST = ("оператор", "специалист", "человек", "поддержк")
_ERROR_MARKERS = ("ошиб", "проблем", "сбой", "не работа", "не открыва", "не загружа", "не подписыва", "не отобража")
_DEFINITION_PREFIXES = ("что такое", "что это", "определени")
_NAVIGATION_PREFIXES = ("где", "куда", "в каком разделе", "как найти")
_RULES_MARKERS = ("правил", "регламент", "требован", "услови", "порядок")


def _norm(value: str) -> str:
    return " ".join(normalize_query(value).split())


def _tokens(value: str) -> set[str]:
    return {word.casefold() for word in _WORDS.findall(value) if len(word) > 2 and word.casefold() not in _STOP}


@dataclass(frozen=True)
class DomainLexicon:
    """Versioned, local object terms built from corpus/taxonomy labels."""

    version: str = "corpus-v1"
    objects: tuple[str, ...] = ()

    @classmethod
    def from_chunks(cls, chunks: Iterable[dict], version: str = "corpus-v1") -> "DomainLexicon":
        phrases: set[str] = set()
        keys = ("title", "category", "service", "section", "topic", "subtopic", "task_name")
        for chunk in chunks:
            metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
            for key in keys:
                value = chunk.get(key) or metadata.get(key)
                if not isinstance(value, str):
                    continue
                normalized = _norm(value)
                words = _tokens(normalized)
                # Labels with one meaningful word are useful; long prose titles
                # are not object names and would overfit retrieval documents.
                if normalized and 1 <= len(words) <= 6:
                    phrases.add(normalized)
        return cls(version=version, objects=tuple(sorted(phrases, key=lambda item: (-len(item), item))))

    def match(self, query: str) -> str | None:
        normalized = _norm(query)
        query_terms = _tokens(normalized)
        best: tuple[float, str] | None = None
        for phrase in self.objects:
            phrase_terms = _tokens(phrase)
            if not phrase_terms:
                continue
            if phrase in normalized:
                score = 2.0 + len(phrase_terms) / 100
            else:
                overlap = len(query_terms & phrase_terms)
                # Require every meaningful term for short taxonomy labels, or
                # a strong majority for longer labels. This avoids matching a
                # document merely because of a generic verb.
                # A multi-word instructional title is not an object synonym:
                # matching just its noun would confuse unrelated actions.
                required = len(phrase_terms)
                if overlap < required:
                    continue
                score = overlap / len(phrase_terms)
            if best is None or score > best[0]:
                best = (score, phrase)
        return best[1] if best else None

    def to_dict(self) -> dict:
        return {"version": self.version, "objects": list(self.objects)}


@dataclass(frozen=True)
class IntentFrame:
    intent: str = "unknown"
    object: str | None = None
    object_subtype: str | None = None
    action: str | None = None
    stage: str | None = None
    error_text: str | None = None
    error_code: str | None = None
    user_role: str | None = None
    missing_slots: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.0

    def to_dict(self) -> dict:
        value = asdict(self)
        value["missing_slots"] = list(self.missing_slots)
        return value


def action_from_text(query: str) -> str | None:
    normalized = _norm(query)
    for action, stems in _ACTION_CLASSES.items():
        if any(stem in normalized for stem in stems):
            return action
    return None


def extract_intent_frame(query: str, lexicon: DomainLexicon) -> IntentFrame:
    normalized = _norm(query)
    obj = lexicon.match(normalized)
    action = action_from_text(normalized)
    error_match = re.search(r"\b(?:код\s*)?(\d{3,}|[a-z]{2,}\d+)\b", normalized, flags=re.IGNORECASE)
    error_code = error_match.group(1) if error_match else None
    has_error = error_code is not None or any(marker in normalized for marker in _ERROR_MARKERS)
    if any(marker in normalized for marker in _HUMAN_REQUEST):
        intent = "human_request"
    elif normalized.startswith(_DEFINITION_PREFIXES):
        intent = "definition"
    elif has_error:
        intent = "troubleshooting"
    elif normalized.startswith(_NAVIGATION_PREFIXES) or action == "find_open":
        intent = "navigation"
    elif any(marker in normalized for marker in _RULES_MARKERS):
        intent = "rules"
    elif action or normalized.startswith("как "):
        intent = "how_to"
    elif obj:
        # A recognised object without an operation is a topic, not a how-to.
        intent = "unknown"
    else:
        intent = "unknown"

    missing: list[str] = []
    if intent == "definition" and not obj:
        missing.append("object")
    elif intent == "how_to":
        if not obj:
            missing.append("object")
        if not action:
            missing.append("action")
    elif intent == "navigation" and not obj:
        missing.append("object_or_goal")
    elif intent == "troubleshooting":
        if not obj:
            missing.append("object")
        if not has_error:
            missing.append("symptom")
        elif not error_code and len(_tokens(normalized)) <= 5:
            missing.append("error_text_or_stage")
    elif intent == "rules" and not obj:
        missing.append("subject")
    elif intent == "unknown":
        missing.append("action" if obj else "object_or_goal")

    confidence = 0.15 + (0.45 if obj else 0.0) + (0.25 if action or has_error else 0.0)
    if intent == "human_request":
        confidence = 1.0
    return IntentFrame(intent=intent, object=obj, action=action, error_text=normalized if has_error else None,
                       error_code=error_code, missing_slots=tuple(missing), confidence=min(confidence, 0.95))
