"""Build a reproducible RAG-quality evaluation set from verified silver links.

Positive cases deliberately reuse only source IDs already checked against the
canonical corpus.  This script creates no synthetic gold answers: variations
change the user wording, never the cited evidence.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluation.dataset import load_jsonl, save_jsonl_atomic


SOURCE = ROOT / "data" / "eval" / "retrieval_eval_silver.jsonl"
OUTPUT = ROOT / "data" / "eval" / "rag_quality_eval.jsonl"
CANONICAL = ROOT / "data" / "processed" / "index" / "all_chunks.jsonl"
POSITIVE_INDEXES = (0, 3, 4, 5, 6, 7, 8, 13, 14, 17, 19, 20, 24, 27, 31)

PARAPHRASES = {
    0: "где в личном кабинете прикрепить машиночитаемую доверенность",
    3: "в каком разделе добавить xml доверенности",
    7: "что нужно сделать поставщику для регистрации на портале",
    8: "как восстановить доступ к кабинету поставщика",
    13: "почему не отображается активная котировочная сессия",
    14: "какими способами можно сформировать оферту",
    17: "кто вправе быть поставщиком на портале",
    20: "инструкция по подписанию электронного акта",
    24: "можно ли убрать оферту в статусе черновика",
    27: "разрешено ли менять закупку после ее завершения",
}

TYPOS = {
    0: "как дабавить мчд",
    3: "куда загруит доверенность",
    7: "как зарегестрироватся поставщику",
    8: "не палучается вайти в личный кабинет",
    13: "не открываеться катировочная сессия",
    14: "как саздать аферту",
    24: "как удалить черновик аферты",
    31: "падписываеться аферта с ашипкой",
}


def positive_case(source: dict, *, case_id: str, category: str, query: str | None = None) -> dict:
    return {
        "id": case_id, "category": category, "query": query or source["query"],
        "route": source.get("route"), "expected_decision": "ANSWER",
        "relevant_document_ids": list(source["relevant_document_ids"]),
        "relevant_chunk_ids": list(source["relevant_chunk_ids"]),
        "label_source": "derived_from_verified_silver", "reference_query": source["query"],
    }


def negative_case(case_id: str, category: str, query: str, decision: str) -> dict:
    return {
        "id": case_id, "category": category, "query": query, "expected_decision": decision,
        "relevant_document_ids": [], "relevant_chunk_ids": [], "label_source": "manual_negative_no_gold_answer",
    }


def validate(rows: list[dict]) -> None:
    chunk_ids, document_ids = set(), set()
    for line in CANONICAL.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        chunk_ids.add(item["chunk_id"])
        document_ids.add(item["document_id"])
    assert len(rows) == 50, f"expected 50 cases, got {len(rows)}"
    assert len({row["id"] for row in rows}) == len(rows)
    for row in rows:
        for document_id in row["relevant_document_ids"]:
            assert document_id in document_ids, f"unknown document {document_id}"
        for chunk_id in row["relevant_chunk_ids"]:
            assert chunk_id in chunk_ids, f"unknown chunk {chunk_id}"
        if row["expected_decision"] == "ANSWER":
            assert row["relevant_document_ids"] or row["relevant_chunk_ids"], row["id"]
        else:
            assert not row["relevant_document_ids"] and not row["relevant_chunk_ids"], row["id"]


def main() -> None:
    source = load_jsonl(SOURCE)
    rows: list[dict] = []
    for index in POSITIVE_INDEXES:
        rows.append(positive_case(source[index], case_id=f"direct_{index}", category="direct"))
    for index, query in PARAPHRASES.items():
        rows.append(positive_case(source[index], case_id=f"paraphrase_{index}", category="paraphrase", query=query))
    for index, query in TYPOS.items():
        rows.append(positive_case(source[index], case_id=f"typo_{index}", category="typo", query=query))
    for index in (3, 6, 20):
        rows.append(positive_case(source[index], case_id=f"multi_chunk_{index}", category="multi_chunk"))
    rows.extend([
        negative_case("ambiguous_signing", "ambiguous", "не могу подписать", "NEEDS_CLARIFICATION"),
        negative_case("ambiguous_contract", "ambiguous", "правила работы с контрактом", "NEEDS_CLARIFICATION"),
        negative_case("ambiguous_attorney", "ambiguous", "доверенность", "NEEDS_CLARIFICATION"),
        negative_case("missing_feature", "missing_knowledge", "неизвестная функция портала", "ESCALATE_TO_OPERATOR"),
        negative_case("missing_operator", "missing_knowledge", "как связаться с оператором", "ESCALATE_TO_OPERATOR"),
        negative_case("missing_taxonomy", "missing_knowledge", "где посмотреть темы обращений", "ESCALATE_TO_OPERATOR"),
        negative_case("missing_upd_definition", "missing_knowledge", "что такое УПД", "ESCALATE_TO_OPERATOR"),
        negative_case("missing_http500", "missing_knowledge", "ошибка 500 при открытии оферты", "ESCALATE_TO_OPERATOR"),
        negative_case("near_miss_fee", "near_miss", "какая комиссия портала за размещение оферты", "ESCALATE_TO_OPERATOR"),
        negative_case("near_miss_duration", "near_miss", "сколько дней длится котировочная сессия", "ESCALATE_TO_OPERATOR"),
        negative_case("near_miss_manager", "near_miss", "как узнать телефон личного менеджера", "ESCALATE_TO_OPERATOR"),
        negative_case("adversarial_penalty", "adversarial_grounding", "назови точный штраф за неподписание оферты", "ESCALATE_TO_OPERATOR"),
        negative_case("adversarial_deadline", "adversarial_grounding", "какой точный срок ответа технической поддержки", "ESCALATE_TO_OPERATOR"),
        negative_case("adversarial_rule", "adversarial_grounding", "процитируй правило портала о комиссии за сделку", "ESCALATE_TO_OPERATOR"),
    ])
    validate(rows)
    save_jsonl_atomic(OUTPUT, rows, backup=False)
    print(f"Wrote {len(rows)} cases to {OUTPUT}")


if __name__ == "__main__":
    main()
