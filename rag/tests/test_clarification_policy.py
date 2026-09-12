from __future__ import annotations

import pytest

from src.application.clarification import ClarificationPolicy
from src.application.pipeline import RAGService


@pytest.mark.parametrize(
    ("query", "route", "reason"),
    [
        ("\u043d\u0435 \u043c\u043e\u0433\u0443 \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u0442\u044c", "L1", "SHORT_FAILURE_QUERY"),
        ("\u043d\u0435 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442", "L3", "SHORT_FAILURE_QUERY"),
        ("\u043f\u0440\u0430\u0432\u0438\u043b\u0430 \u0440\u0430\u0431\u043e\u0442\u044b \u0441 \u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442\u043e\u043c", "L2", "BROAD_POLICY_QUERY"),
    ],
)
def test_ambiguity_policy_detects_narrow_clarification_cases(query, route, reason):
    decision = ClarificationPolicy().evaluate(query, route)
    assert decision.triggered is True
    assert decision.reason == reason


@pytest.mark.parametrize(
    ("query", "route"),
    [
        ("\u043a\u0430\u043a \u0434\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u041c\u0427\u0414", "L1"),
        ("\u043a\u0430\u043a \u0443\u0434\u0430\u043b\u0438\u0442\u044c \u043e\u0444\u0435\u0440\u0442\u0443", "L1"),
        ("\u043a\u0430\u043a\u0438\u0435 \u043f\u0440\u0430\u0432\u0438\u043b\u0430 \u0434\u0435\u0439\u0441\u0442\u0432\u0443\u044e\u0442 \u043f\u0440\u0438 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0438 \u0446\u0435\u043d\u044b \u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442\u0430", "L2"),
    ],
)
def test_ambiguity_policy_does_not_block_specific_or_informational_queries(query, route):
    assert ClarificationPolicy().evaluate(query, route).triggered is False


def test_ambiguity_policy_clarifies_underspecified_lifecycle_action():
    result = ClarificationPolicy().evaluate("разрешено ли исправить закупку после завершения", "L1")
    assert result.triggered is True
    assert result.reason == "UNDERSPECIFIED_LIFECYCLE_ACTION"


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("\u043a\u0430\u043a \u044d\u0442\u043e \u0438\u0441\u043f\u0440\u0430\u0432\u0438\u0442\u044c", "UNRESOLVED_REFERENCE"),
        ("\u0433\u0434\u0435 \u044d\u0442\u043e \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u0442\u044c", "UNRESOLVED_REFERENCE"),
        ("\u0447\u0442\u043e \u0434\u0435\u043b\u0430\u0442\u044c \u0441 \u041c\u0427\u0414", "UNDERSPECIFIED_ACTION_REQUEST"),
        ("\u043e\u0448\u0438\u0431\u043a\u0430 \u043f\u0440\u0438 \u0437\u0430\u0433\u0440\u0437\u043a\u0435 XML", "AMBIGUOUS_XML_WORKFLOW"),
        ("\u043c\u043e\u0436\u043d\u043e \u043b\u0438 \u043e\u0442\u043c\u0435\u043d\u0438\u0442\u044c \u0443\u0436\u0435 \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u043d\u043e\u0435", "UNDERSPECIFIED_LIFECYCLE_OBJECT"),
        ("\u043d\u0435 \u043c\u043e\u0433\u0443 \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u0442\u044c \u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442 \u0447\u0442\u043e \u0434\u0435\u043b\u0430\u0442\u044c", "UNDERSPECIFIED_FAILURE_CONTEXT"),
    ],
)
def test_ambiguity_policy_clarifies_general_underspecified_requests(query, reason):
    decision = ClarificationPolicy().evaluate(query, "L1")
    assert decision.triggered is True
    assert decision.reason == reason


class Retriever:
    def __init__(self, candidates):
        self.candidates = candidates
        self.calls = 0

    def retrieve_with_trace(self, _query, technical=False):
        self.calls += 1
        return {"results": self.candidates, "official_bm25": [], "official_dense": [], "timing": {}}


class Generator:
    def __init__(self):
        self.calls = 0

    def answer(self, evidence):
        self.calls += 1
        return {"answer": evidence[0]["text"], "used_evidence": True}


def _official(score=.99):
    return {"chunk_id": "o", "document_id": "o", "text": "official", "source_type": "official_manual", "authority": "official", "score": score, "metadata": {}}


def test_ambiguity_policy_overrides_high_retrieval_score_before_retrieval():
    retriever, generator = Retriever([_official()]), Generator()
    result = RAGService(retriever, generator=generator).ask("\u043d\u0435 \u043c\u043e\u0433\u0443 \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u0442\u044c")
    assert result["status"] == "NEEDS_CLARIFICATION"
    assert retriever.calls == generator.calls == 0
    assert result["diagnostics"]["clarification_reason"] == "SHORT_FAILURE_QUERY"
    assert result["diagnostics"]["retrieval_mode"] == "NONE"


def test_profanity_gate_runs_before_clarification_policy():
    class FailingPolicy:
        def evaluate(self, *_args):
            raise AssertionError("clarification policy must not run after profanity")

    result = RAGService(Retriever([_official()]), clarification_policy=FailingPolicy()).ask("\u044d\u0442\u043e \u0445\u0443\u0439\u043d\u044f")
    assert result["status"] == "REFUSE_PROFANITY"


def test_policy_disabled_keeps_normal_strong_evidence_answer_and_low_evidence_escalates():
    disabled = ClarificationPolicy(enabled=False)
    assert RAGService(Retriever([_official()]), clarification_policy=disabled).ask("\u043a\u0430\u043a \u0434\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u041c\u0427\u0414")["status"] == "ANSWER"
    assert RAGService(Retriever([]), clarification_policy=disabled).ask("\u043a\u0430\u043a \u0434\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u041c\u0427\u0414")["status"] == "ESCALATE_TO_OPERATOR"
