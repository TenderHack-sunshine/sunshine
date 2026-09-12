"""HTTP adapter that translates the existing RAG service into the Go contract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.application.factory import build_rag_service
from src.core.config import Settings
from src.moderation.profanity import detect_profanity


class ServiceNotReadyError(RuntimeError):
    """Raised when a local artifact required by the RAG service is absent."""


@dataclass
class RAGAPI:
    service: Any

    @classmethod
    def from_settings(cls, settings: Settings) -> "RAGAPI":
        try:
            return cls(service=build_rag_service(settings))
        except FileNotFoundError as error:
            raise ServiceNotReadyError(f"RAG startup dependency is unavailable: {error}") from error

    def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        if payload.get("moderation_only") is True:
            prepared = self.service.preprocessor.process(query)
            if prepared["moderation"]["contains_profanity"]:
                return {"status": "blocked", "blocked_reason": self.service.ask(query)["answer"], "sources": []}
            # The backend uses this endpoint solely to decide whether it may
            # append a message to an operator ticket.  Do not retrieve or
            # generate an answer for clean follow-ups.
            return {"status": "answered", "answer": "", "sources": []}
        result = self.service.ask(_contextual_query(query, payload.get("context")))
        sources = [_source(item) for item in result.get("sources", [])]
        topic = _topic(result.get("sources", []))
        status = result.get("status")

        if status == "ANSWER":
            return {
                "status": "answered",
                "answer": result["answer"],
                "support_level": result.get("route") or "L1",
                "sources": sources,
                **({"topic": topic} if topic else {}),
            }
        if status == "NEEDS_CLARIFICATION":
            return {
                "status": "need_clarification",
                "clarification_question": result["answer"],
                "sources": [],
            }
        if status in {"REFUSE_PROFANITY", "REJECTED_PROFANITY"}:
            return {
                "status": "blocked",
                "blocked_reason": result["answer"],
                "sources": [],
            }
        if status == "ESCALATE_TO_OPERATOR":
            return {
                "status": "escalated",
                "answer": result["answer"],
                "support_level": result.get("route") or "L2",
                "confidence": 0.0,
                "sources": sources,
                **({"topic": topic} if topic else {}),
            }
        raise RuntimeError(f"unsupported RAG status: {status!r}")


def _contextual_query(query: str, context: Any) -> str:
    """Attach one safe prior user topic only for a short follow-up.

    The current message remains the only message that is moderated as a new
    input.  Profane history is never copied into the query, which fixes the
    earlier poisoned-conversation bug while preserving context for requests
    such as "а точнее" or "добавить" after a question about МЧД.
    """
    normalized = " ".join(query.casefold().split())
    tokens = normalized.split()
    explicit_follow_up = (
        normalized in {"а точнее", "точнее", "подробнее", "детальнее", "как это", "а если", "а дальше"}
        or (len(tokens) <= 2 and any(token in {"добавить", "заменить", "отозвать", "подписать", "загрузить", "да"} for token in tokens))
    )
    # A short status report ("выходит ошибка", "не работает") needs the
    # preceding user topic to formulate a useful clarification.  It is not an
    # answer by itself, so never send it through retrieval without that topic.
    contextual_status = len(tokens) <= 4 and (
        normalized.startswith(("выходит ошиб", "появилась ошиб", "та же ошиб", "снова ошиб"))
        or normalized in {"работа", "ошибка", "не работает", "не получается", "не могу", "не входит"}
    )
    if not (explicit_follow_up or contextual_status) or not isinstance(context, list):
        return query
    skipped_current = False
    for item in reversed(context):
        if not isinstance(item, dict) or item.get("sender_type") != "USER":
            continue
        previous = str(item.get("text", "")).strip()
        if not previous:
            continue
        if not skipped_current and previous == query:
            skipped_current = True
            continue
        if detect_profanity(previous)["contains_profanity"]:
            continue
        return f"{previous}\nУточнение к предыдущей теме: {query}"
    return query
def _source(item: dict[str, Any]) -> dict[str, Any]:
    document = str(item.get("source_path") or item.get("source") or item.get("document_id") or "knowledge-base")
    page = item.get("page_start") if item.get("page_start") is not None else item.get("page")
    return {
        "document": document,
        "section": str(item.get("section") or item.get("title") or ""),
        "chunk_id": str(item.get("chunk_id") or document),
        **({"page": page} if page is not None else {}),
    }


def _topic(items: list[dict[str, Any]]) -> str | None:
    for item in items:
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            continue
        for key in ("topic", "category", "task_name", "service"):
            value = str(metadata.get(key) or "").strip()
            if value:
                return value
    return None
