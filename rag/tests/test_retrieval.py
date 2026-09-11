from src.retrieval.hybrid import HybridRetriever, reciprocal_rank_fusion


def test_rrf_fuses_by_chunk_id():
    fused = reciprocal_rank_fusion([[{"chunk_id": "a", "text": "A"}, {"chunk_id": "b", "text": "B"}], [{"chunk_id": "b", "text": "B"}]])
    assert fused[0]["chunk_id"] == "b"


def test_retrieval_has_public_result_format_and_prefers_manual():
    docs = [
        {"chunk_id": "manual", "text": "Как добавить новую доверенность в профиле поставщика", "source": "manual.pdf", "page": 11, "section": "Доверенности", "authority": "manual"},
        {"chunk_id": "ticket", "text": "доверенность исправлено", "source": "support_ticket", "authority": "historical_ticket", "answer_quality": "low"},
    ]
    result = HybridRetriever(docs).search("Как добавить доверенность", top_k=2)
    assert set(result[0]) == {"score", "text", "source", "page", "section", "authority", "chunk_id"}
    assert result[0]["authority"] == "manual"
