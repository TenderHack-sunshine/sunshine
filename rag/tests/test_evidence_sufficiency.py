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


def test_explicit_navigation_evidence_keeps_answerable_mchd_request_answerable():
    result = _service("В разделе Профиль пользователя откройте доверенности, нажмите Добавить МЧД и загрузите XML.").ask("как добавить МЧД")
    assert result["status"] == "ANSWER"
    assert result["diagnostics"]["evidence_sufficiency"]["sufficient"] is True


def test_disabled_checker_preserves_current_default_behaviour():
    result = RAGService(Retriever("Тема обращений: Работа с СТЕ.")).ask("где посмотреть темы обращений")
    assert result["status"] == "ANSWER"
    assert result["diagnostics"]["evidence_sufficiency"]["reason"] == "DISABLED"


def test_contact_request_requires_an_explicit_contact_path():
    result = _service("Войдите в личный кабинет по логину и паролю.").ask("как связаться с персональным менеджером")
    assert result["status"] == "ESCALATE_TO_OPERATOR"
    assert result["diagnostics"]["evidence_sufficiency"]["reason"] == "CONTACT_PATH_NOT_EXPLICIT"


def test_generic_support_contact_does_not_prove_a_personal_manager_contact():
    result = _service(
        "\u041e\u0431\u0440\u0430\u0442\u0438\u0442\u0435\u0441\u044c \u0432 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0443 \u043f\u043e \u044d\u043b\u0435\u043a\u0442\u0440\u043e\u043d\u043d\u043e\u0439 \u043f\u043e\u0447\u0442\u0435."
    ).ask("\u043a\u0430\u043a \u0441\u0432\u044f\u0437\u0430\u0442\u044c\u0441\u044f \u0441 \u043f\u0435\u0440\u0441\u043e\u043d\u0430\u043b\u044c\u043d\u044b\u043c \u043c\u0435\u043d\u0435\u0434\u0436\u0435\u0440\u043e\u043c")
    assert result["status"] == "ESCALATE_TO_OPERATOR"
    assert result["diagnostics"]["evidence_sufficiency"]["reason"] == "CONTACT_TARGET_NOT_EXPLICIT"


def test_figure_caption_is_not_numeric_evidence_for_a_penalty_amount():
    result = _service(
        "\u0420\u0438\u0441\u0443\u043d\u043e\u043a 1. \u0417\u0430\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u0435 \u0441\u0443\u043c\u043c\u044b \u0448\u0442\u0440\u0430\u0444\u043e\u0432 \u0432 \u0441\u043f\u0435\u0446\u0438\u0444\u0438\u043a\u0430\u0446\u0438\u0438."
    ).ask("\u043a\u0430\u043a\u043e\u0439 \u0448\u0442\u0440\u0430\u0444 \u043d\u0430\u0447\u0438\u0441\u043b\u044f\u0442 \u0437\u0430 \u043f\u0440\u043e\u0441\u0440\u043e\u0447\u043a\u0443 \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u0438\u044f \u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442\u0430?")
    assert result["status"] == "ESCALATE_TO_OPERATOR"
    assert result["diagnostics"]["evidence_sufficiency"]["reason"] == "REQUESTED_NUMBER_NOT_EXPLICIT"


def test_action_evidence_does_not_prove_absence_of_consequences():
    result = _service(
        "\u041e\u0444\u0435\u0440\u0442\u0443 \u043c\u043e\u0436\u043d\u043e \u043e\u0442\u043e\u0437\u0432\u0430\u0442\u044c \u0434\u043e \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u043f\u0440\u0438\u0451\u043c\u0430 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0439."
    ).ask("\u043c\u043e\u0436\u043d\u043e \u043b\u0438 \u043e\u0442\u043c\u0435\u043d\u0438\u0442\u044c \u043e\u0444\u0435\u0440\u0442\u0443 \u0431\u0435\u0437 \u043f\u043e\u0441\u043b\u0435\u0434\u0441\u0442\u0432\u0438\u0439?")
    assert result["status"] == "ESCALATE_TO_OPERATOR"
    assert result["diagnostics"]["evidence_sufficiency"]["reason"] == "CONSEQUENCE_NOT_EXPLICIT"


def test_procedural_question_is_not_mistaken_for_an_exact_fact_question():
    result = _service("При ошибке подписания оферты обратитесь в техническую поддержку и приложите скриншот.").ask(
        "какой порядок действий при ошибке подписания оферты"
    )
    assert result["status"] == "ANSWER"
