from __future__ import annotations

from src.application.clarification import ClarificationPolicy
from src.application.pipeline import QueryPreprocessor, RAGService
from src.faq.cards import FAQCard, FAQStore, chunk_fingerprint
from src.safety.profanity import ProfanityResult


class Detector:
    backend = "rule"

    def detect(self, _query):
        return ProfanityResult(False, 0.0, 1.0)


class NeverRetrieve:
    def retrieve_with_trace(self, *_args, **_kwargs):
        raise AssertionError("a verified FAQ should answer before retrieval")


def _chunk(text="Котировочная сессия — процедура выбора поставщика."):
    return {"chunk_id": "official:definition", "document_id": "kb:definition", "text": text,
            "authority": "official", "source_type": "official_kb", "source_path": "kb.json",
            "title": "Котировочная сессия", "metadata": {}}


def _card(chunk, **changes):
    values = {
        "id": "faq:quote", "intent": "quote_session_definition", "title": "Котировочная сессия",
        "question_variants": ("Что такое котировочная сессия?",),
        "answer": "Котировочная сессия — процедура выбора поставщика.", "role": "supplier",
        "source_chunk_ids": (chunk["chunk_id"],), "source_urls": (), "verified": True,
        "review_status": "VERIFIED", "reviewed_by": "reviewer", "reviewed_at": "2026-01-01",
        "updated_at": "2026-01-01", "source_fingerprints": {chunk["chunk_id"]: chunk_fingerprint(chunk)},
    }
    values.update(changes)
    return FAQCard(**values)


def test_pending_faq_card_is_never_used_at_runtime():
    chunk = _chunk()
    store = FAQStore([_card(chunk, verified=False, review_status="PENDING_HUMAN_REVIEW")], [chunk])
    assert store.match("Что такое котировочная сессия?") is None


def test_verified_current_official_faq_card_is_used_before_rag():
    chunk = _chunk()
    store = FAQStore([_card(chunk)], [chunk])
    service = RAGService(NeverRetrieve(), preprocessor=QueryPreprocessor(Detector()),
                         clarification_policy=ClarificationPolicy(enabled=False), faq_store=store)
    response = service.ask("Что такое котировочная сессия?")
    assert response["status"] == "ANSWER"
    assert response["diagnostics"]["faq_used"] is True
    assert response["sources"][0]["chunk_id"] == chunk["chunk_id"]


def test_changed_faq_source_requires_review_and_cannot_match():
    original = _chunk()
    changed = _chunk("Котировочная сессия изменилась.")
    store = FAQStore([_card(original)], [changed])
    assert store.validation_error(store.cards[0]) == "SOURCE_CHANGED_REVIEW_REQUIRED"
    assert store.match("Что такое котировочная сессия?") is None
