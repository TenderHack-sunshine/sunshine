from __future__ import annotations

"""Create disjoint, human-reviewable DEV and FINAL abstention-label queues.

The records deliberately keep ``label`` unset.  Proposed labels and cited
evidence make a review practical, but must not be used to tune or certify a
policy until a human reviewer records a decision.
"""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = {
    "DEV": ROOT / "data/eval/abstention_calibration_dev.jsonl",
    "FINAL": ROOT / "data/eval/abstention_calibration_final.jsonl",
}
CANONICAL = ROOT / "data/processed/index/all_chunks.jsonl"


SOURCES = {
    "mchd": ("zakupki_kb:559615", "zakupki_kb:559615:0", "Profile section and XML power-of-attorney upload steps."),
    "registration": ("zakupki_kb:563652", "zakupki_kb:563652:0", "Supplier registration overview and required registration path."),
    "login": ("zakupki_kb:559705", "zakupki_kb:559705:0", "Documented path for restoring access to a personal account."),
    "quotation": ("zakupki_kb:559982", "zakupki_kb:559982:0", "Why an active quotation session may not display."),
    "offer_create": ("zakupki_kb:225884", "zakupki_kb:225884:0", "Supported ways to create and publish offers / STE."),
    "supplier": ("zakupki_kb:576047", "zakupki_kb:576047:0", "Who can act as a supplier on the portal."),
    "act": ("local:76a3d7498623c29bc3d70e982e64cdee7f13dcb9", None, "Electronic execution manual describes the act/UPD workflow."),
    "draft": ("zakupki_kb:225669", "zakupki_kb:225669:0", "Draft offers cannot be deleted; the documented alternative is archiving."),
    "purchase": ("zakupki_kb:562811", "zakupki_kb:562811:0", "Conditions under which a purchase may be changed or withdrawn."),
    "offer_error": ("zakupki_kb:559611", "zakupki_kb:559611:0", "Documented escalation path for a technical error while signing an offer."),
    "mass_sign": ("zakupki_kb:226081", "zakupki_kb:226081:0", "Mass-offer-signing navigation and operation steps."),
    "offer_definition": ("zakupki_kb:352057", "zakupki_kb:352057:0", "Definition of an offer and its stated maximum validity."),
}


DEV_ANSWERABLE = [
    ("direct", "Как в профиле прикрепить машиночитаемую доверенность?", "mchd", ["profile location", "XML upload action"]),
    ("paraphrase", "Где загружается XML-файл доверенности для сотрудника?", "mchd", ["XML upload field", "add action"]),
    ("typo", "как дабавить мчд", "mchd", ["MChD attachment steps"]),
    ("direct", "С чего начать регистрацию организации как поставщика?", "registration", ["registration path"]),
    ("paraphrase", "Что делать, если не удаётся войти в кабинет поставщика?", "login", ["access recovery path"]),
    ("direct", "Почему не вижу действующую котировочную сессию?", "quotation", ["display troubleshooting"]),
    ("direct", "Какими способами на портале можно оформить оферту?", "offer_create", ["supported creation methods"]),
    ("direct", "Кто имеет право работать поставщиком через портал?", "supplier", ["eligible supplier types"]),
    ("direct", "Как оформить электронный акт в портале?", "act", ["act/UPD workflow"]),
    ("direct", "Можно ли удалить оферту, пока она в черновиках?", "draft", ["deletion unavailable", "archive alternative"]),
    ("direct", "Разрешено ли исправить закупку после её завершения?", "purchase", ["change/withdrawal conditions"]),
    ("technical", "При подписании оферты появилась ошибка: какой предусмотрен порядок действий?", "offer_error", ["technical-error escalation path"]),
    ("direct", "Можно ли подписать несколько оферт за один раз?", "mass_sign", ["mass signing is available", "navigation steps"]),
    ("direct", "Что считается офертой на Портале поставщиков?", "offer_definition", ["offer definition"]),
    ("direct", "Какой максимальный срок действия оферты указан в справке?", "offer_definition", ["maximum three-month validity"]),
    ("paraphrase", "В каком меню управлять сразу группой оферт для подписания?", "mass_sign", ["offer-management navigation"]),
    ("typo", "не аткрываецца катировачная сессия", "quotation", ["display troubleshooting"]),
    ("paraphrase", "Как восстановить доступ пользователя к личному кабинету?", "login", ["access recovery path"]),
    ("direct", "Что вместо удаления черновой оферты предлагает портал?", "draft", ["archive alternative"]),
    ("paraphrase", "Какая информация нужна, чтобы понять, могу ли я быть поставщиком?", "supplier", ["eligible supplier types"]),
]

FINAL_ANSWERABLE = [
    ("direct", "Где в карточке пользователя добавить МЧД?", "mchd", ["profile location", "MChD attachment"]),
    ("paraphrase", "Подскажите путь для загрузки доверенности в XML.", "mchd", ["XML upload field"]),
    ("typo", "как зарегестрироватся паставщику", "registration", ["registration path"]),
    ("direct", "Как вернуть доступ к учётной записи поставщика?", "login", ["access recovery path"]),
    ("direct", "Из-за чего может не отображаться активная котировочная сессия?", "quotation", ["display troubleshooting"]),
    ("direct", "Как создать оферту или СТЕ доступным способом?", "offer_create", ["supported creation methods"]),
    ("direct", "Какие лица могут зарегистрироваться как поставщики?", "supplier", ["eligible supplier types"]),
    ("paraphrase", "Опишите порядок работы с актом в электронном исполнении.", "act", ["act/UPD workflow"]),
    ("direct", "Что произойдёт, если попытаться удалить черновик оферты?", "draft", ["deletion unavailable", "archive alternative"]),
    ("direct", "В какой момент разрешено отредактировать или отозвать закупку?", "purchase", ["change/withdrawal conditions"]),
    ("technical", "Оферта не подписывается из-за технической ошибки — что указано в базе знаний?", "offer_error", ["technical-error escalation path"]),
    ("direct", "Есть ли на портале массовое подписание оферт?", "mass_sign", ["mass signing is available"]),
    ("direct", "Какие обязательные свойства есть у оферты согласно справке?", "offer_definition", ["offer definition", "essential terms"]),
    ("direct", "Сколько месяцев может действовать опубликованная оферта?", "offer_definition", ["maximum three-month validity"]),
    ("paraphrase", "Как открыть список оферт и выбрать несколько для подписания?", "mass_sign", ["offer-management navigation", "selection steps"]),
    ("typo", "как удалит черновик аферты", "draft", ["archive alternative"]),
    ("paraphrase", "Мне нужна инструкция по первичной регистрации на портале.", "registration", ["registration path"]),
    ("direct", "Как понять, доступна ли мне роль поставщика?", "supplier", ["eligible supplier types"]),
    ("direct", "Где описано прикрепление МЧД к сотруднику?", "mchd", ["MChD attachment"]),
    ("paraphrase", "Какие варианты предлагает база знаний для создания новой оферты?", "offer_create", ["supported creation methods"]),
]

DEV_UNANSWERABLE = [
    ("partial_knowledge", "Где посмотреть полный список тем обращений в поддержку?", "INSUFFICIENT_KNOWLEDGE", "PARTIAL_KNOWLEDGE", "Taxonomy rows exist, but no authoritative user-facing navigation instruction is cited."),
    ("near_miss", "Какая комиссия взимается за публикацию оферты?", "INSUFFICIENT_KNOWLEDGE", "PARTIAL_KNOWLEDGE", "Offer procedures do not state a commission or its amount."),
    ("adversarial", "Назовите точную сумму штрафа за неподписание оферты.", "INSUFFICIENT_KNOWLEDGE", "PARTIAL_KNOWLEDGE", "Offer material does not establish an exact penalty."),
    ("partial_knowledge", "Какой максимальный срок действия МЧД разрешён законом?", "INSUFFICIENT_KNOWLEDGE", "PARTIAL_KNOWLEDGE", "The corpus explains upload, not the requested legal validity limit."),
    ("no_relevant_documents", "Как связаться с моим персональным менеджером портала?", "INSUFFICIENT_KNOWLEDGE", "NO_RELEVANT_DOCUMENTS", "No verified contact procedure or personal-manager directory is in the corpus."),
    ("no_relevant_documents", "Что означает код HTTP 500 при открытии оферты?", "INSUFFICIENT_KNOWLEDGE", "NO_RELEVANT_DOCUMENTS", "No verified explanation for a generic HTTP 500 is present."),
    ("near_miss", "Сколько минут длится котировочная сессия?", "INSUFFICIENT_KNOWLEDGE", "PARTIAL_KNOWLEDGE", "The corpus discusses quotation workflows, not a universal duration."),
    ("no_relevant_documents", "Какая комиссия удерживается при оплате через портал?", "INSUFFICIENT_KNOWLEDGE", "NO_RELEVANT_DOCUMENTS", "No payment-fee policy is established in the corpus."),
    ("partial_knowledge", "Какой штраф начислят за просрочку подписания контракта?", "INSUFFICIENT_KNOWLEDGE", "PARTIAL_KNOWLEDGE", "Related contract material does not establish the requested amount."),
    ("no_relevant_documents", "Когда оператор поддержки ответит на моё обращение?", "INSUFFICIENT_KNOWLEDGE", "NO_RELEVANT_DOCUMENTS", "No service-level response time is verified."),
    ("ambiguous", "Не получается подписать.", "AMBIGUOUS_QUERY", None, "The object, step, and error are unspecified."),
    ("ambiguous", "Нужна помощь с доверенностью.", "AMBIGUOUS_QUERY", None, "Upload, use, and validation are distinct tasks."),
    ("ambiguous", "Правила работы с контрактом.", "AMBIGUOUS_QUERY", None, "The request lacks a task or contract stage."),
    ("near_miss", "Можно ли отменить уже подписанную оферту без последствий?", "INSUFFICIENT_KNOWLEDGE", "PARTIAL_KNOWLEDGE", "Documents discuss lifecycle actions but do not establish the requested consequence."),
    ("no_relevant_documents", "Где скачать мобильное приложение портала?", "INSUFFICIENT_KNOWLEDGE", "NO_RELEVANT_DOCUMENTS", "No mobile-app distribution information is verified."),
]

FINAL_UNANSWERABLE = [
    ("partial_knowledge", "Какая юридическая сила у загруженной МЧД?", "INSUFFICIENT_KNOWLEDGE", "PARTIAL_KNOWLEDGE", "Upload instructions do not establish legal effect."),
    ("near_miss", "Сколько стоит размещение одной оферты?", "INSUFFICIENT_KNOWLEDGE", "PARTIAL_KNOWLEDGE", "Offer documentation does not state a price or fee."),
    ("adversarial", "Процитируйте правило портала о комиссии за сделку.", "INSUFFICIENT_KNOWLEDGE", "NO_RELEVANT_DOCUMENTS", "No verified commission rule is available."),
    ("partial_knowledge", "Какой срок хранения МЧД в личном кабинете?", "INSUFFICIENT_KNOWLEDGE", "PARTIAL_KNOWLEDGE", "The corpus covers attachment, not retention period."),
    ("no_relevant_documents", "Как изменить номер телефона оператора, закреплённого за мной?", "INSUFFICIENT_KNOWLEDGE", "NO_RELEVANT_DOCUMENTS", "No personal-operator assignment data is verified."),
    ("no_relevant_documents", "Почему портал не работает именно в моём регионе?", "INSUFFICIENT_KNOWLEDGE", "NO_RELEVANT_DOCUMENTS", "No region-specific availability evidence is present."),
    ("near_miss", "Какой фиксированный срок есть на подписание любой оферты?", "INSUFFICIENT_KNOWLEDGE", "PARTIAL_KNOWLEDGE", "The corpus does not establish one universal deadline for all offers."),
    ("partial_knowledge", "Как оспорить штраф за отказ от оферты?", "INSUFFICIENT_KNOWLEDGE", "PARTIAL_KNOWLEDGE", "Related offer documents do not establish an appeal process for that penalty."),
    ("no_relevant_documents", "Можно ли оплатить комиссию банковской картой?", "INSUFFICIENT_KNOWLEDGE", "NO_RELEVANT_DOCUMENTS", "No commission-payment flow is verified."),
    ("no_relevant_documents", "Как узнать график работы оператора поддержки?", "INSUFFICIENT_KNOWLEDGE", "NO_RELEVANT_DOCUMENTS", "No support-hours source is verified."),
    ("ambiguous", "Ошибка в оферте.", "AMBIGUOUS_QUERY", None, "No error text, state, or operation is supplied."),
    ("ambiguous", "Не открывается раздел.", "AMBIGUOUS_QUERY", None, "The section and observable symptom are unknown."),
    ("ambiguous", "Нужен договор.", "AMBIGUOUS_QUERY", None, "It does not identify the user's needed action."),
    ("near_miss", "Что будет, если не подписать оферту в последний день?", "INSUFFICIENT_KNOWLEDGE", "PARTIAL_KNOWLEDGE", "Related offer instructions do not establish the requested consequence."),
    ("no_relevant_documents", "Как подключить двухфакторную аутентификацию?", "INSUFFICIENT_KNOWLEDGE", "NO_RELEVANT_DOCUMENTS", "No verified two-factor-authentication procedure is present."),
]


def answer_record(split: str, ordinal: int, spec: tuple) -> dict:
    category, query, source_key, facts = spec
    document_id, chunk_id, span = SOURCES[source_key]
    return {
        "id": f"{split.lower()}_answer_{ordinal:02}", "split": split, "category": category, "query": query,
        "label": None, "proposed_label": "ANSWERABLE", "gap_type": None,
        "review_status": "PENDING_HUMAN_REVIEW", "reviewer": None,
        "supporting_evidence": [{"document_id": document_id, "chunk_id": chunk_id,
                                  "minimal_evidence_span": span, "expected_facts": facts}],
        "label_rationale": "Proposed from a cited official source; a reviewer must verify the span and label.",
    }


def abstention_record(split: str, ordinal: int, spec: tuple) -> dict:
    category, query, proposed_label, gap_type, rationale = spec
    return {
        "id": f"{split.lower()}_abstain_{ordinal:02}", "split": split, "category": category, "query": query,
        "label": None, "proposed_label": proposed_label, "gap_type": gap_type,
        "review_status": "PENDING_HUMAN_REVIEW", "reviewer": None,
        "supporting_evidence": [], "label_rationale": rationale,
    }


def validate(rows: list[dict]) -> None:
    chunks, documents = set(), set()
    for line in CANONICAL.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        chunks.add(item["chunk_id"])
        documents.add(item["document_id"])
    assert len(rows) == 35
    assert len({row["id"] for row in rows}) == len(rows)
    assert all(row["label"] is None and row["review_status"] == "PENDING_HUMAN_REVIEW" for row in rows)
    for row in rows:
        for evidence in row["supporting_evidence"]:
            assert evidence["document_id"] in documents
            if evidence["chunk_id"] is not None:
                assert evidence["chunk_id"] in chunks


def main() -> None:
    sets = {
        "DEV": [*(answer_record("DEV", i, row) for i, row in enumerate(DEV_ANSWERABLE, 1)),
                *(abstention_record("DEV", i, row) for i, row in enumerate(DEV_UNANSWERABLE, 1))],
        "FINAL": [*(answer_record("FINAL", i, row) for i, row in enumerate(FINAL_ANSWERABLE, 1)),
                  *(abstention_record("FINAL", i, row) for i, row in enumerate(FINAL_UNANSWERABLE, 1))],
    }
    queries = {split: {row["query"] for row in rows} for split, rows in sets.items()}
    assert not queries["DEV"] & queries["FINAL"], "DEV and FINAL queries must be disjoint"
    for split, rows in sets.items():
        validate(rows)
        OUTPUTS[split].write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        print(f"{split}: {len(rows)} pending-review cases -> {OUTPUTS[split]}")


if __name__ == "__main__":
    main()
