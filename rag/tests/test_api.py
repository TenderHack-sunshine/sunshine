from src.api import RAGAPI
from src.generation.generator import EvidenceGenerator


class Service:
    def __init__(self, result):
        self.result = result
        self.query = None

    def ask(self, query):
        self.query = query
        return self.result


def test_api_maps_answer_and_sources_to_backend_contract():
    service = Service({
        "status": "ANSWER", "answer": "Откройте раздел доверенностей.", "route": "L1",
        "sources": [{
            "chunk_id": "kb:42", "source_path": "https://example.test/guide", "title": "Доверенности",
            "page_start": 4,
        }],
    })
    result = RAGAPI(service).process({"query": "Как добавить доверенность?"})

    assert result["status"] == "answered"
    assert result["sources"] == [{"document": "https://example.test/guide", "section": "Доверенности", "chunk_id": "kb:42", "page": 4}]


def test_generator_accepts_a_dense_candidate_with_raw_score_only():
    result = EvidenceGenerator().answer([{"text": "Official dense evidence", "raw_score": .7, "authority": "official"}])
    assert result["used_evidence"] is True


def test_api_maps_existing_service_statuses():
    cases = [
        ("REFUSE_PROFANITY", "blocked"),
        ("NEEDS_CLARIFICATION", "need_clarification"),
        ("ESCALATE_TO_OPERATOR", "escalated"),
    ]
    for source_status, expected_status in cases:
        result = RAGAPI(Service({"status": source_status, "answer": "message", "route": "L2", "sources": []})).process({"query": "Вопрос"})
        assert result["status"] == expected_status


def test_api_passes_user_conversation_to_existing_service():
    service = Service({"status": "NEEDS_CLARIFICATION", "answer": "Уточните", "sources": []})
    RAGAPI(service).process({
        "query": "Ошибка 42",
        "context": [
            {"sender_type": "USER", "text": "Не работает подпись"},
            {"sender_type": "AI", "text": "Уточните"},
            {"sender_type": "USER", "text": "Ошибка 42"},
        ],
    })
    assert service.query == "Не работает подпись\nОшибка 42"
