"""HTTP adapter for the Supplier Portal backend.

It only exposes the existing local RAG pipeline; retrieval and answer
generation remain in their respective modules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from src.core.config import Settings
from src.generation.generator import EvidenceGenerator
from src.main import answer_question
from src.moderation.profanity import detect_profanity
from src.retrieval.mvp import load_two_path_retriever


class ServiceNotReadyError(RuntimeError):
    """Raised when local knowledge-base artifacts have not been built yet."""


@dataclass
class RAGAPI:
    retriever: Any
    generator: EvidenceGenerator

    @classmethod
    def from_settings(cls, settings: Settings) -> "RAGAPI":
        canonical_path = settings.processed_dir / "index" / "all_chunks.jsonl"
        if not canonical_path.exists():
            raise ServiceNotReadyError(
                f"Canonical corpus is missing: {canonical_path}. Run scripts/prepare_index.py first."
            )
        ticket_index = settings.root_dir / "data" / "indexes" / "support_tickets_bm25.pkl"
        return cls(
            retriever=load_two_path_retriever(canonical_path, ticket_index if ticket_index.exists() else None),
            generator=EvidenceGenerator(settings.min_evidence_score),
        )

    def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = str(payload.get("message", "")).strip()
        if not message:
            raise ValueError("message is required")
        moderation = detect_profanity(message)
        if moderation["contains_profanity"]:
            return {
                "status": "blocked",
                "blocked_reason": "Обращение заблокировано из-за недопустимой лексики.",
                "topic": "moderation",
                "support_level": "L1",
                "sources": [],
            }

        result = answer_question(message, self.retriever, generator=self.generator)
        route = result["route"] or {}
        taxonomy = route.get("taxonomy") or {}
        technical = route.get("technical") or {}
        topic = taxonomy.get("topic") or technical.get("intent") or "unknown"
        evidence = result.get("evidence", [])
        if not result["used_evidence"]:
            return {
                "status": "escalated",
                "answer": result["answer"],
                "topic": topic,
            "support_level": "L3" if technical.get("technical") else "L2",
                "confidence": 0.0,
                "sources": [],
            }
        return {
            "status": "answered",
            "answer": result["answer"],
            "topic": topic,
            "support_level": evidence[0].get("support_level") or "L1",
            "confidence": evidence[0].get("score", 0.0),
            "sources": [_source(item) for item in evidence],
        }


def _source(item: dict[str, Any]) -> dict[str, Any]:
    source = str(item.get("source_path") or item.get("source") or "knowledge-base")
    page = item.get("page_start") if item.get("page_start") is not None else item.get("page")
    return {
        "document_id": str(item.get("chunk_id") or source),
        "title": str(item.get("title") or item.get("section") or source),
        "url": source if source.startswith(("https://", "http://")) else f"source://{quote(source)}",
        **({"page": page} if page is not None else {}),
    }
