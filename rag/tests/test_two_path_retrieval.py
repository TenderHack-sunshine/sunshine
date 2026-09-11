from __future__ import annotations

from src.retrieval.bm25 import RussianBM25Retriever, tokenize
from src.retrieval.mvp import TwoPathRetriever
from src.routing.normalization import normalize_query
from src.routing.technical import TechnicalRouter


def _chunk(chunk_id, text, source_type, authority, document_id=None):
    return {
        "chunk_id": chunk_id, "document_id": document_id or chunk_id, "text": text, "source_type": source_type,
        "authority": authority, "metadata": {"topic": "МЧД", "subtopic": "Добавление"},
    }


def test_russian_bm25_normalizes_yo_and_preserves_common_schema():
    retriever = RussianBM25Retriever([_chunk("a", "Добавление машиночитаемой доверенности", "support_ticket", "case_history")])
    result = retriever.search("добавить МЧД")
    assert result[0]["chunk_id"] == "a"
    assert set(result[0]) >= {"chunk_id", "text", "source_type", "authority", "score", "retrieval_method", "metadata"}
    assert tokenize("ёжик") == tokenize("ежик")


def test_two_path_prefers_official_and_only_adds_tickets_for_technical_query():
    chunks = [
        _chunk("official", "Как добавить МЧД в профиль поставщика", "official_manual", "official", "manual"),
        _chunk("ticket-1", "Ошибка при добавлении МЧД исправляется после загрузки XML", "support_ticket", "case_history", "ticket-a"),
        _chunk("ticket-2", "Ошибка при добавлении МЧД повторяется", "support_ticket", "case_history", "ticket-a"),
    ]
    retriever = TwoPathRetriever.from_canonical(chunks)
    nontechnical = retriever.search("как добавить мчд", top_k=5)
    assert [item["source_type"] for item in nontechnical] == ["official_manual"]
    technical = retriever.search("ошибка при добавлении мчд", top_k=5)
    assert technical[0]["source_type"] == "official_manual"
    assert sum(item["source_type"] == "support_ticket" for item in technical) == 1
    assert all(item["retrieval_method"] == "bm25" for item in technical)


def test_technical_results_reserve_one_diverse_ticket_when_official_has_many_hits():
    chunks = [_chunk(f"official-{index}", "Ошибка при добавлении МЧД", "official_manual", "official", f"official-{index}") for index in range(8)]
    chunks.append(_chunk("ticket", "Ошибка при добавлении МЧД решена", "support_ticket", "case_history", "ticket"))
    results = TwoPathRetriever.from_canonical(chunks).search("ошибка при добавлении мчд", top_k=5)
    assert results[0]["source_type"] == "official_manual"
    assert any(item["source_type"] == "support_ticket" for item in results)


def test_typo_and_technical_routing_are_local_and_deterministic():
    assert normalize_query("Как зарегестрироваться?!!") == "как зарегистрироваться"
    decision = TechnicalRouter().classify("Не открывается котировочная сессия: ошибка 500")
    assert decision["technical"] is True
