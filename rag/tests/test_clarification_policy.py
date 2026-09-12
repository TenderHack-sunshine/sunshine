from __future__ import annotations

import pytest

from src.application.clarification import ClarificationPolicy
from src.application.pipeline import RAGService


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("работа", "MISSING_SUBJECT_OR_STAGE"),
        ("не работает", "MISSING_SUBJECT_OR_STAGE"),
        ("выходит ошибка", "MISSING_ERROR_DETAILS"),
        ("Как это исправить", "MISSING_REFERENT"),
        ("Что делать с МЧД", "MISSING_ACTION"),
        ("МЧД", "MISSING_ACTION"),
        ("Ошибка при загрузке файла\nУточнение к предыдущей теме: выходит ошибка", "MISSING_ERROR_DETAILS"),
    ],
)
def test_clarifies_only_when_the_turn_lacks_required_context(query, reason):
    decision = ClarificationPolicy().evaluate(query, "L3")
    assert decision.triggered is True
    assert decision.reason == reason


@pytest.mark.parametrize(
    "query",
    [
        "Ошибка при загрузке файла",
        "Ошибка при загрузке XML",
        "Как добавить МЧД",
        "Не открывается котировочная сессия",
        "Как создать оферту",
        "Правила работы с контрактом",
    ],
)
def test_concrete_request_does_not_receive_a_clarification(query):
    assert ClarificationPolicy().evaluate(query, "L3").triggered is False


class Retriever:
    def __init__(self, candidates):
        self.candidates = candidates
        self.calls = 0

    def retrieve_with_trace(self, _query, technical=False):
        self.calls += 1
        return {"results": self.candidates, "official_bm25": [], "official_dense": [], "timing": {}}


def _official():
    return {"chunk_id": "o", "document_id": "o", "text": "official instruction", "source_type": "official_manual", "authority": "official", "score": .99, "metadata": {}}


def test_vague_follow_up_stops_before_retrieval_and_requests_details():
    retriever = Retriever([_official()])
    result = RAGService(retriever).ask("Ошибка при загрузке файла\nУточнение к предыдущей теме: выходит ошибка")
    assert result["status"] == "NEEDS_CLARIFICATION"
    assert "какой файл" in result["answer"]
    assert retriever.calls == 0


def test_concrete_short_failure_reaches_the_answer_pipeline():
    retriever = Retriever([_official()])
    result = RAGService(retriever).ask("Ошибка при загрузке XML")
    assert result["status"] == "ANSWER"
    assert retriever.calls == 1
