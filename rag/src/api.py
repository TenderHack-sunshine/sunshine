"""HTTP adapter that translates the existing RAG service into the Go contract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.application.factory import build_rag_service
from src.core.config import Settings
from src.safety.profanity import ProfanityModelLoadError


class ServiceNotReadyError(RuntimeError):
    """Raised when a local artifact required by the RAG service is absent."""


@dataclass
class RAGAPI:
    service: Any

    @classmethod
    def from_settings(cls, settings: Settings) -> "RAGAPI":
        try:
            return cls(service=build_rag_service(settings))
        except (FileNotFoundError, ProfanityModelLoadError) as error:
            raise ServiceNotReadyError(f"RAG startup dependency is unavailable: {error}") from error

    def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        user_messages = _user_messages(payload.get("context"))
        retrieval_query = "\n".join(dict.fromkeys([*user_messages, query]))
        result = self.service.ask(retrieval_query)
        sources = [_source(item) for item in result.get("sources", [])]
        status = result.get("status")

        if status == "ANSWER":
            return {
                "status": "answered",
                "answer": result["answer"],
                "support_level": result.get("route") or "L1",
                "sources": sources,
            }
        if status == "NEEDS_CLARIFICATION":
            return {
                "status": "need_clarification",
                "clarification_question": result["answer"],
                "sources": [],
            }
        if status == "REFUSE_PROFANITY":
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
            }
        raise RuntimeError(f"unsupported RAG status: {status!r}")


def _user_messages(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    messages = []
    for item in value:
        if not isinstance(item, dict) or item.get("sender_type") != "USER":
            continue
        text = str(item.get("text", "")).strip()
        if text:
            messages.append(text)
    return messages


def _source(item: dict[str, Any]) -> dict[str, Any]:
    document = str(item.get("source_path") or item.get("source") or item.get("document_id") or "knowledge-base")
    page = item.get("page_start") if item.get("page_start") is not None else item.get("page")
    return {
        "document": document,
        "section": str(item.get("section") or item.get("title") or ""),
        "chunk_id": str(item.get("chunk_id") or document),
        **({"page": page} if page is not None else {}),
    }
