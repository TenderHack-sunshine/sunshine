from src.api import RAGAPI
from src.generation.generator import EvidenceGenerator
from src.application.pipeline import QueryPreprocessor
from src.safety.profanity import ProfanityResult


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


def test_api_moderates_and_retrieves_only_the_current_user_message():
    service = Service({"status": "NEEDS_CLARIFICATION", "answer": "Уточните", "sources": []})
    RAGAPI(service).process({
        "query": "Ошибка 42",
        "context": [
            {"sender_type": "USER", "text": "Не работает подпись"},
            {"sender_type": "AI", "text": "Уточните"},
            {"sender_type": "USER", "text": "Ошибка 42"},
        ],
    })
    assert service.query == "Ошибка 42"


def test_profane_history_cannot_poison_a_clean_follow_up():
    class ModeratingService(Service):
        def ask(self, query):
            self.query = query
            return {
                "status": "REFUSE_PROFANITY" if "блять" in query.casefold() else "ANSWER",
                "answer": "blocked" if "блять" in query.casefold() else "clean answer",
                "route": "L1", "sources": [],
            }

    service = ModeratingService({})
    result = RAGAPI(service).process({
        "query": "Как добавить МЧД?",
        "context": [{"sender_type": "USER", "text": "блять, не работает"}],
    })
    assert result["status"] == "answered"
    assert service.query == "Как добавить МЧД?"


def test_short_follow_up_uses_only_the_previous_safe_user_topic():
    service = Service({"status": "NEEDS_CLARIFICATION", "answer": "Уточните", "sources": []})
    RAGAPI(service).process({
        "query": "а точнее",
        "context": [
            {"sender_type": "USER", "text": "Работа с МЧД"},
            {"sender_type": "AI", "text": "Что именно нужно сделать?"},
            {"sender_type": "USER", "text": "а точнее"},
        ],
    })
    assert service.query == "Работа с МЧД\nУточнение к предыдущей теме: а точнее"


def test_short_error_status_uses_the_previous_safe_user_topic():
    service = Service({"status": "NEEDS_CLARIFICATION", "answer": "Уточните", "sources": []})
    RAGAPI(service).process({
        "query": "выходит ошибка",
        "context": [
            {"sender_type": "USER", "text": "Ошибка при загрузке файла"},
            {"sender_type": "AI", "text": "Проверьте обязательные поля"},
            {"sender_type": "USER", "text": "выходит ошибка"},
        ],
    })
    assert service.query == "Ошибка при загрузке файла\nУточнение к предыдущей теме: выходит ошибка"


def test_moderation_only_blocks_without_retrieval_or_generation():
    class Detector:
        backend = "rule"

        def detect(self, query):
            return ProfanityResult("хуй" in query.casefold(), 1.0, 1.0)

    class ModerationService(Service):
        def __init__(self):
            super().__init__({})
            self.preprocessor = QueryPreprocessor(Detector())

        def ask(self, query):
            self.query = query
            return {"status": "REFUSE_PROFANITY", "answer": "Переформулируйте без нецензурной лексики."}

    service = ModerationService()
    result = RAGAPI(service).process({"query": "хуй", "moderation_only": True})
    assert result == {"status": "blocked", "blocked_reason": "Переформулируйте без нецензурной лексики.", "sources": []}


def test_profane_prior_message_is_not_used_as_follow_up_context():
    service = Service({"status": "ANSWER", "answer": "clean", "route": "L1", "sources": []})
    RAGAPI(service).process({
        "query": "подробнее",
        "context": [
            {"sender_type": "USER", "text": "блять, не работает"},
            {"sender_type": "USER", "text": "подробнее"},
        ],
    })
    assert service.query == "подробнее"
