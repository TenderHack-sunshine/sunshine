from __future__ import annotations

from src.application.pipeline import ConfidenceEvaluator, RAGService, SupportRouter
from src.core.config import Settings
from src.routing.normalization import normalize_query


class FakeRetriever:
    def __init__(self, candidates=None):
        self.candidates = candidates or []
        self.technical_calls = []

    def retrieve_with_trace(self, _query, technical=False):
        self.technical_calls.append(technical)
        return {"results": self.candidates, "dense_available": False, "fallback_used": True,
                "timing": {"bm25_ms": 1.0, "fusion_ms": 1.0}}


def _source(kind="official_manual", authority="official"):
    return {"chunk_id": "c", "document_id": "d", "text": "Инструкция по добавлению МЧД", "source_type": kind,
            "authority": authority, "retrieval_method": "bm25", "raw_score": 3.0, "rrf_score": .01, "metadata": {}}


def test_profanity_is_a_hard_exit_before_routing_or_retrieval():
    class Context:
        def needs_clarification(self, _query):
            raise AssertionError("clarification must not run for profanity")

    class Router:
        def classify(self, _query):
            raise AssertionError("routing must not run for profanity")

    retriever = FakeRetriever([_source()])
    result = RAGService(retriever, context=Context(), router=Router()).ask("блять не работает")
    assert result["status"] == "REFUSE_PROFANITY"
    assert retriever.technical_calls == []
    assert result["sources"] == []
    assert result["diagnostics"]["retrieval_mode"] == "NONE"


def test_underspecified_error_needs_clarification_before_retrieval():
    retriever = FakeRetriever([_source()])
    result = RAGService(retriever).ask("не работает")
    assert result["status"] == "NEEDS_CLARIFICATION"
    assert retriever.technical_calls == []


def test_routes_l1_l2_and_l3_deterministically():
    router = SupportRouter()
    assert router.classify("как добавить мчд")["route"] == "L1"
    assert router.classify("требования к участнику")["route"] == "L2"
    assert router.classify("не подписывается оферта")["route"] == "L3"
    assert normalize_query("падписывается аферта с ашипкой") == "подписывается оферта с ошибкой"


def test_l3_calls_ticket_capable_retriever_and_sources_are_attributed():
    retriever = FakeRetriever([_source(), {**_source("support_ticket", "case_history"), "chunk_id": "ticket", "document_id": "ticket", "text": "Историческое решение ошибки подписи"}])
    result = RAGService(retriever).ask("не подписывается оферта")
    assert result["status"] == "ANSWER"
    assert result["route"] == "L3"
    assert retriever.technical_calls == [True]
    assert result["sources"][1]["authority"] == "case_history"


def test_insufficient_evidence_escalates_and_reranker_failure_falls_back():
    class BrokenReranker:
        def rerank(self, *_args):
            raise RuntimeError("unavailable")

    empty = RAGService(FakeRetriever(), reranker=BrokenReranker(), rerank_enabled=True).ask("как добавить мчд")
    assert empty["status"] == "ESCALATE_TO_OPERATOR"
    usable = RAGService(FakeRetriever([_source()]), reranker=BrokenReranker(), rerank_enabled=True).ask("как добавить мчд")
    assert usable["status"] == "ANSWER"
    assert usable["diagnostics"]["reranker_used"] is False


def test_optional_reranker_can_reorder_hybrid_candidates():
    class OrderingReranker:
        available = True
        last_latency_ms = 2.0

        @staticmethod
        def rerank(_query, candidates, _top_k):
            return [{**candidates[-1], "reranker_score": .9}, {**candidates[0], "reranker_score": .1}]

    first, second = _source(), {**_source(), "chunk_id": "second", "document_id": "second", "text": "Другая инструкция"}
    result = RAGService(FakeRetriever([first, second]), reranker=OrderingReranker(), rerank_enabled=True).ask("как добавить мчд")
    assert result["diagnostics"]["reranker_used"] is True
    assert result["sources"][0]["chunk_id"] == "second"


def test_partial_qdrant_index_is_ignored_and_complete_index_is_activated(monkeypatch):
    import src.application.factory as factory

    class Store:
        points = 1

        def __init__(self, *_args):
            pass

        def collection_exists(self):
            return True

        def count(self):
            return self.points

    monkeypatch.setattr(factory, "HttpQdrantStore", Store)
    settings = Settings(official_expected_points=2)
    assert factory.official_dense_if_ready(settings) is None
    Store.points = 2
    assert factory.official_dense_if_ready(settings) is not None


def test_ambiguous_query_uses_clarification_policy_before_retrieval():
    retriever = FakeRetriever([_source()])
    result = RAGService(retriever).ask("не работает")
    assert result["status"] == "NEEDS_CLARIFICATION"
    assert retriever.technical_calls == []


def test_no_evidence_escalates_and_strong_official_evidence_answers():
    assert RAGService(FakeRetriever()).ask("как добавить мчд")["status"] == "ESCALATE_TO_OPERATOR"
    assert RAGService(FakeRetriever([_source()])).ask("как добавить мчд")["status"] == "ANSWER"


def test_low_official_agreement_can_clarify_when_explicitly_configured():
    evaluator = ConfidenceEvaluator(min_agreement=.5)
    features = {"top_score": .9, "official_evidence_present": True, "num_ticket_candidates": 0, "retrieval_agreement": 0.0}
    assert evaluator.decide("L1", [_source()], features) == ("NEEDS_CLARIFICATION", "official_retrieval_agreement_below_threshold")
