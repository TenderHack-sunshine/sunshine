from src.api import RAGAPI
from src.generation.generator import EvidenceGenerator
from src.application.pipeline import QueryPreprocessor
from src.routing.intent import DomainLexicon
from src.safety.profanity import ProfanityResult


class Service:
    def __init__(self, result, objects=()):
        self.result = result
        self.query = None
        self.lexicon = DomainLexicon(objects=tuple(objects))

    def ask(self, query):
        self.query = query
        return self.result


def test_api_maps_answer_and_sources_to_backend_contract():
    service = Service({"status": "ANSWER", "answer": "answer", "route": "L1", "sources": [{"chunk_id": "kb:42", "source_path": "guide", "title": "section", "page_start": 4}]})
    result = RAGAPI(service).process({"query": "how to create record"})
    assert result["status"] == "answered"
    assert result["sources"] == [{"document": "guide", "section": "section", "chunk_id": "kb:42", "page": 4}]
    assert result["dialog_state"]["resolved_query"]


def test_generator_accepts_a_dense_candidate_with_raw_score_only():
    assert EvidenceGenerator().answer([{"text": "Official dense evidence", "raw_score": .7, "authority": "official"}])["used_evidence"]


def test_api_offers_handoff_instead_of_creating_a_ticket():
    result = RAGAPI(Service({"status": "ESCALATE_TO_OPERATOR", "answer": "message", "route": "L2", "sources": []})).process({"query": "question"})
    assert result["status"] == "offer_handoff"
    assert result["dialog_state"]["handoff_offered"] is True


def test_api_uses_persisted_slots_not_context_concatenation():
    service = Service({"status": "ANSWER", "answer": "ok", "route": "L1", "sources": []}, objects=("экспериментальный реестр",))
    first = RAGAPI(service).process({"query": "экспериментальный реестр"})
    assert first["dialog_state"]["pending_clarification"] == ["action"]
    second = RAGAPI(service).process({"query": "добавить", "dialog_state": first["dialog_state"], "context": [{"text": "untrusted old history"}]})
    assert service.query == "добавить экспериментальный реестр"
    assert "untrusted" not in service.query


def test_api_confirmed_handoff_and_direct_human_request():
    service = Service({"status": "ESCALATE_TO_OPERATOR", "answer": "message", "route": "L2", "sources": []})
    offered = RAGAPI(service).process({"query": "unknown question"})
    confirmed = RAGAPI(service).process({"query": "да", "dialog_state": offered["dialog_state"]})
    assert confirmed["status"] == "escalate_confirmed"
    direct = RAGAPI(Service({})).process({"query": "нужен оператор"})
    assert direct["status"] == "escalate_confirmed"


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
            return {"status": "REFUSE_PROFANITY", "answer": "rephrase"}

    service = ModerationService()
    assert RAGAPI(service).process({"query": "хуй", "moderation_only": True}) == {"status": "blocked", "blocked_reason": "rephrase", "sources": []}
