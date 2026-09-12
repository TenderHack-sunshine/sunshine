from src.api import RAGAPI
from src.generation.generator import EvidenceGenerator


class Retriever:
    def __init__(self, evidence):
        self.evidence = evidence

    def search(self, _query, technical=False):
        return self.evidence


def test_api_maps_existing_evidence_to_backend_contract():
    api = RAGAPI(
        retriever=Retriever([{
            "chunk_id": "kb:42", "text": "Откройте раздел доверенностей.", "score": .9,
            "source_path": "https://example.test/guide", "title": "Доверенности",
            "page_start": 4, "authority": "official", "support_level": "L1",
        }]),
        generator=EvidenceGenerator(),
    )

    result = api.process({"message": "Как добавить доверенность?"})

    assert result["status"] == "answered"
    assert result["sources"] == [{"document_id": "kb:42", "title": "Доверенности", "url": "https://example.test/guide", "page": 4}]


def test_generator_accepts_a_dense_candidate_with_raw_score_only():
    result = EvidenceGenerator().answer([{"text": "Official dense evidence", "raw_score": .7, "authority": "official"}])
    assert result["used_evidence"] is True


def test_api_blocks_profanity_without_retrieval():
    result = RAGAPI(retriever=Retriever([]), generator=EvidenceGenerator()).process({"message": "Это х*йня"})
    assert result["status"] == "blocked"
    assert result["sources"] == []


def test_api_escalates_when_confidence_gate_has_no_evidence():
    result = RAGAPI(retriever=Retriever([]), generator=EvidenceGenerator()).process({"message": "Нужна помощь"})
    assert result["status"] == "escalated"
    assert result["confidence"] == 0.0
