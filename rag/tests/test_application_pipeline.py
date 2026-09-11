from __future__ import annotations

from src.application.pipeline import RAGService, SupportRouter
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
    retriever = FakeRetriever([_source()])
    result = RAGService(retriever).ask("блять не работает")
    assert result["status"] == "REJECTED_PROFANITY"
    assert retriever.technical_calls == []
    assert result["sources"] == []


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
    retriever = FakeRetriever([_source(), _source("support_ticket", "case_history")])
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
