"""Route tickets from the versioned support taxonomy, never retrieval rank."""
from __future__ import annotations

from dataclasses import dataclass

from src.routing.intent import IntentFrame, _tokens


@dataclass(frozen=True)
class TicketRoute:
    topic: str | None = None
    subtopic: str | None = None
    support_level: str | None = None
    matched_taxonomy_id: str | None = None
    confidence: float = 0.0
    reason: str = "no_taxonomy_match"

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class TicketRouter:
    """A conservative taxonomy matcher for handoff metadata.

    A missing line in the spreadsheet deliberately stays unassigned: the
    generic L1/L2/L3 policy is not claimed to be an approved taxonomy.
    """
    def __init__(self, taxonomy_chunks: list[dict]):
        self.rows = [item for item in taxonomy_chunks if item.get("source_type") == "support_taxonomy"]

    def route(self, frame: IntentFrame, query: str) -> TicketRoute:
        terms = _tokens(" ".join(part for part in (query, frame.object or "", frame.action or "") if part))
        best: tuple[float, dict] | None = None
        for item in self.rows:
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            labels = " ".join(str(metadata.get(key) or "") for key in ("topic", "subtopic"))
            label_terms = _tokens(labels)
            if not terms or not label_terms:
                continue
            score = len(terms & label_terms) / len(label_terms)
            if score and (best is None or score > best[0]):
                best = (score, item)
        if best is None or best[0] < 0.5:
            return TicketRoute(reason="low_taxonomy_confidence")
        item = best[1]
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        line = str(metadata.get("support_level") or "").strip() or None
        return TicketRoute(topic=metadata.get("topic") or None, subtopic=metadata.get("subtopic") or None,
                           support_level=line, matched_taxonomy_id=item.get("chunk_id"), confidence=best[0],
                           reason="taxonomy_label_overlap" if line else "taxonomy_match_line_pending_human_review")
