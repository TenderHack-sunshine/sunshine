"""Small, local, review-gated FAQ card store.

FAQ is an optimisation, not a second source of truth: a runtime answer is
eligible only if every cited chunk still exists and is official.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path


_TOKEN = re.compile(r"[\w\-]+", re.UNICODE)
_STOP = {"как", "что", "это", "где", "для", "или", "при", "про", "мне", "нужно", "можно"}


def _terms(value: str) -> set[str]:
    return {word.casefold() for word in _TOKEN.findall(value) if len(word) > 2 and word.casefold() not in _STOP}


def chunk_fingerprint(chunk: dict) -> str:
    return sha256(str(chunk.get("text", "")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FAQCard:
    id: str
    intent: str
    title: str
    question_variants: tuple[str, ...]
    answer: str
    role: str | None = None
    source_chunk_ids: tuple[str, ...] = ()
    source_urls: tuple[str, ...] = ()
    verified: bool = False
    review_status: str = "PENDING_HUMAN_REVIEW"
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    updated_at: str | None = None
    source_fingerprints: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict) -> "FAQCard":
        return cls(
            id=str(value["id"]), intent=str(value.get("intent", "")), title=str(value.get("title", "")),
            question_variants=tuple(str(item) for item in value.get("question_variants", [])), answer=str(value.get("answer", "")),
            role=value.get("role"), source_chunk_ids=tuple(str(item) for item in value.get("source_chunk_ids", [])),
            source_urls=tuple(str(item) for item in value.get("source_urls", [])), verified=bool(value.get("verified", False)),
            review_status=str(value.get("review_status", "PENDING_HUMAN_REVIEW")), reviewed_by=value.get("reviewed_by"),
            reviewed_at=value.get("reviewed_at"), updated_at=value.get("updated_at"),
            source_fingerprints={str(key): str(item) for key, item in dict(value.get("source_fingerprints", {})).items()},
        )

    def to_dict(self) -> dict:
        return asdict(self)


class FAQStore:
    def __init__(self, cards: list[FAQCard], canonical_chunks: list[dict]):
        self.cards = cards
        self.chunks = {str(chunk.get("chunk_id")): chunk for chunk in canonical_chunks}

    @classmethod
    def from_jsonl(cls, path: str | Path, canonical_chunks: list[dict]) -> "FAQStore":
        file_path = Path(path)
        cards = [] if not file_path.is_file() else [FAQCard.from_dict(json.loads(line)) for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return cls(cards, canonical_chunks)

    def validation_error(self, card: FAQCard) -> str | None:
        if not card.verified or card.review_status != "VERIFIED":
            return "NOT_VERIFIED"
        if not card.answer.strip() or not card.source_chunk_ids:
            return "MISSING_ANSWER_OR_SOURCES"
        for chunk_id in card.source_chunk_ids:
            chunk = self.chunks.get(chunk_id)
            if not chunk or chunk.get("authority") != "official":
                return "SOURCE_NOT_CURRENT_OFFICIAL_CHUNK"
            expected = card.source_fingerprints.get(chunk_id)
            # A verified answer without a source fingerprint cannot detect a
            # later corpus edit, so it is intentionally not eligible at
            # runtime.  Review tooling must record one for every source.
            if not expected:
                return "SOURCE_FINGERPRINT_REQUIRED"
            if expected != chunk_fingerprint(chunk):
                return "SOURCE_CHANGED_REVIEW_REQUIRED"
        return None

    def match(self, query: str, *, min_score: float = 0.60) -> FAQCard | None:
        query_terms = _terms(query)
        if not query_terms:
            return None
        best: tuple[float, FAQCard] | None = None
        for card in self.cards:
            if self.validation_error(card):
                continue
            variants = [card.title, card.intent, *card.question_variants]
            variant_terms = set().union(*(_terms(value) for value in variants))
            score = len(query_terms & variant_terms) / len(query_terms)
            if score >= min_score and (best is None or score > best[0]):
                best = (score, card)
        return best[1] if best else None

    def sources_for(self, card: FAQCard) -> list[dict]:
        return [self.chunks[chunk_id] for chunk_id in card.source_chunk_ids if chunk_id in self.chunks]
