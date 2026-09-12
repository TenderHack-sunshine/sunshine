"""HTTP adapter between the Go API and the local RAG service."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.application.dialog_state import DialogState, update_dialog_state
from src.application.factory import build_rag_service
from src.core.config import Settings
from src.routing.intent import DomainLexicon, extract_intent_frame


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
            return {"status": "answered", "answer": "", "sources": []}

        # Persisted state stores only confirmed slots.  Full history is not
        # concatenated into a retrieval or generation prompt.
        previous = DialogState.from_dict(payload.get("dialog_state"))
        frame = extract_intent_frame(query, getattr(self.service, "lexicon", DomainLexicon()))
        state = update_dialog_state(previous, frame, query)
        if frame.intent == "human_request":
            return _response("escalate_confirmed", state, answer="Передаю обращение сотруднику поддержки по вашей просьбе.", escalation_reason="direct_human_request", **_ticket_route(self.service, frame, state.resolved_query))
        if previous.handoff_offered and _is_handoff_confirmation(query):
            return _response("escalate_confirmed", state, answer="Передаю обращение сотруднику поддержки.", escalation_reason="handoff_confirmed", **_ticket_route(self.service, frame, state.resolved_query))

        result = self.service.ask(state.resolved_query)
        sources = [_source(item) for item in result.get("sources", [])]
        status = result.get("status")
        if status == "ANSWER":
            return _response("answered", state, answer=result["answer"], support_level=result.get("route") or "L1", sources=sources)
        if status == "NEEDS_CLARIFICATION":
            if state.clarification_count >= 2:
                offered = DialogState(**{**state.to_dict(), "handoff_offered": True})
                return _response("offer_handoff", offered, answer="Мне пока не хватает данных для надёжного ответа. Передать обращение сотруднику поддержки?", escalation_reason="clarification_limit")
            return _response("need_clarification", state, clarification_question=result["answer"], sources=[])
        if status in {"REFUSE_PROFANITY", "REJECTED_PROFANITY"}:
            return _response("blocked", state, blocked_reason=result["answer"], sources=[])
        if status == "ESCALATE_TO_OPERATOR":
            offered = DialogState(**{**state.to_dict(), "handoff_offered": True})
            return _response("offer_handoff", offered, answer="Не нашёл достаточно подтверждённой информации. Передать обращение сотруднику поддержки?", support_level=result.get("route") or "L2", sources=sources, escalation_reason=result.get("diagnostics", {}).get("confidence_reason", "insufficient_evidence"))
        raise RuntimeError(f"unsupported RAG status: {status!r}")


def _is_handoff_confirmation(query: str) -> bool:
    return " ".join(query.casefold().split()) in {"да", "подтверждаю", "передавайте", "передать", "хочу", "согласен"}


def _response(status: str, state: DialogState, **value: Any) -> dict[str, Any]:
    return {"status": status, "dialog_state": state.to_dict(), "resolved_query": state.resolved_query, **value}


def _ticket_route(service: Any, frame: Any, query: str) -> dict[str, Any]:
    router = getattr(service, "ticket_router", None)
    if router is None:
        return {"routing_reason": "taxonomy_unavailable"}
    route = router.route(frame, query)
    return {"topic": route.topic, "subtopic": route.subtopic, "support_level": route.support_level,
            "routing_reason": route.reason, "taxonomy_id": route.matched_taxonomy_id, "routing_confidence": route.confidence}


def _source(item: dict[str, Any]) -> dict[str, Any]:
    document = str(item.get("source_path") or item.get("source") or item.get("document_id") or "knowledge-base")
    page = item.get("page_start") if item.get("page_start") is not None else item.get("page")
    return {
        "document": document,
        "section": str(item.get("section") or item.get("title") or ""),
        "chunk_id": str(item.get("chunk_id") or document),
        **({"page": page} if page is not None else {}),
    }
