from __future__ import annotations

from src.main import answer_question
from src.retrieval.mvp import TwoPathRetriever


def _chunk(chunk_id, text, source_type, authority):
    return {"chunk_id": chunk_id, "document_id": chunk_id, "text": text, "source_type": source_type, "authority": authority, "metadata": {}}


def test_profanity_rejects_before_retrieval():
    retriever = TwoPathRetriever.from_canonical([_chunk("official", "Как создать оферту", "official_manual", "official")])
    response = answer_question("хуй как создать оферту", retriever)
    assert response["used_evidence"] is False
    assert response["evidence"] == []


def test_end_to_end_returns_official_evidence_for_nontechnical_question():
    retriever = TwoPathRetriever.from_canonical([
        _chunk("official", "Как создать оферту на портале", "official_manual", "official"),
        _chunk("ticket", "Ошибка создания оферты", "support_ticket", "case_history"),
    ])
    response = answer_question("Как создать оферту?", retriever)
    assert response["used_evidence"] is True
    assert response["evidence"][0]["source_type"] == "official_manual"
