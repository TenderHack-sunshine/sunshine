from __future__ import annotations

from typing import Protocol


class Retriever(Protocol):
    def retrieve_with_trace(self, query: str, **kwargs) -> dict: ...


class Reranker(Protocol):
    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]: ...


class AnswerGenerator(Protocol):
    def answer(self, evidence: list[dict]) -> dict: ...
