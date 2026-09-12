from __future__ import annotations

from src.application.evidence_sufficiency import EvidenceSufficiencyChecker
from src.application.pipeline import RAGService


class Retriever:
    def __init__(self, text: str):
        self.candidate = {
            "chunk_id": "official:1", "document_id": "official:1", "text": text,
            "authority": "official", "source_type": "official_kb", "raw_score": .82,
        }

    def retrieve_with_trace(self, _query, technical=False):
        return {"results": [self.candidate], "official_dense": [self.candidate], "official_bm25": [], "timing": {}}


def _service(text: str) -> RAGService:
    return RAGService(Retriever(text), evidence_sufficiency=EvidenceSufficiencyChecker(enabled=True))


def test_topic_related_taxonomy_without_navigation_is_not_a_location_answer():
    result = _service("Тема обращений: Работа с СТЕ. Подтема обращений: Ошибка отображения СТЕ.").ask("где посмотреть темы обращений")
    assert result["status"] == "ESCALATE_TO_OPERATOR"
    assert result["diagnostics"]["evidence_sufficiency"]["reason"] == "NAVIGATION_NOT_EXPLICIT"
    assert result["diagnostics"]["knowledge_gap"]["classification"] == "PARTIAL_KNOWLEDGE"


def test_high_similarity_offer_text_does_not_support_missing_commission_fact():
    result = _service("Массовое подписание оферт возможно через раздел Управление офертами.").ask("какая комиссия портала за размещение оферты")
    assert result["status"] == "ESCALATE_TO_OPERATOR"
    assert result["diagnostics"]["evidence_sufficiency"]["reason"] == "REQUESTED_FACT_NOT_EXPLICIT"
    assert "комисси" in result["diagnostics"]["evidence_sufficiency"]["missing_terms"]


def test_near_miss_exact_penalty_without_explicit_penalty_abstains():
    result = _service("Оферта является предложением заключить контракт; срок действия указан в документе.").ask("назови точный штраф за неподписание оферты")
    assert result["status"] == "ESCALATE_TO_OPERATOR"
    assert result["diagnostics"]["evidence_sufficiency"]["reason"] == "REQUESTED_FACT_NOT_EXPLICIT"


def test_unrelated_why_question_abstains_instead_of_reusing_a_generic_portal_match():
    result = _service("Если не отображается страница котировочной сессии, обновите страницу и перезапустите браузер.").ask(
        "почему портал не поддерживает телепортацию заявок на марс"
    )
    assert result["status"] == "ESCALATE_TO_OPERATOR"
    assert result["diagnostics"]["evidence_sufficiency"]["reason"] == "REQUESTED_FACT_NOT_EXPLICIT"


def test_explicit_navigation_evidence_keeps_answerable_mchd_request_answerable():
    result = _service("В разделе Профиль пользователя откройте доверенности, нажмите Добавить МЧД и загрузите XML.").ask("как добавить МЧД")
    assert result["status"] == "ANSWER"
    assert result["diagnostics"]["evidence_sufficiency"]["sufficient"] is True


def test_disabled_checker_preserves_current_default_behaviour():
    result = RAGService(Retriever("Тема обращений: Работа с СТЕ.")).ask("где посмотреть темы обращений")
    assert result["status"] == "ANSWER"
    assert result["diagnostics"]["evidence_sufficiency"]["reason"] == "DISABLED"
