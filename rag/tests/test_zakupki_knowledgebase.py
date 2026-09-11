import json
from pathlib import Path

import pytest

from src.ingestion.parsers.html import clean_html_fragment
from src.ingestion.sources.zakupki_knowledgebase import (
    KnowledgeBaseAPIError,
    classify_support_level,
    chunk_knowledgebase_article,
    ingest_knowledgebase_payload,
    load_payload,
    validate_payload,
)


FIXTURE = Path(__file__).parent / "fixtures" / "zakupki_kb_sample.json"


def _ingested():
    return ingest_knowledgebase_payload(json.loads(FIXTURE.read_text(encoding="utf-8")), base_url="https://zakupki.mos.ru")


def test_traversal_filtering_ids_and_metadata():
    documents, chunks, report = _ingested()
    assert [document["document_id"] for document in documents] == ["zakupki_kb:101", "zakupki_kb:102", "zakupki_kb:103"]
    assert report["articles_total"] == 5
    assert report["articles_ingested"] == 3
    assert report["duplicates"] == 1
    assert report["skipped_reasons"]["not_published"] == 1
    assert all(chunk["chunk_id"].startswith(chunk["document_id"] + ":") for chunk in chunks)
    assert documents[0]["category"] == "Закупочные процедуры"
    assert "createdDate" not in documents[0]["metadata"]


def test_main_text_html_links_images_and_operator_text():
    document = _ingested()[0][0]
    assert "Короткая версия" not in document["text"]
    assert "- перейдите в" in document["text"]
    assert "<p>" not in document["text"]
    assert document["links"] == [{"url": "https://zakupki.mos.ru/registry", "text": "реестр"}]
    assert document["images"][0]["url"] == "https://zakupki.mos.ru/image.png"
    assert document["operator_text"] == "Проверьте роль пользователя."
    assert document["updated_at"] == "2026-07-16T15:01:16"
    assert "createdDate" not in document["metadata"]


def test_support_levels_and_short_article_chunk():
    documents, chunks, report = _ingested()
    assert [document["support_level"] for document in documents] == ["L1", "L2", "L3"]
    assert report["support_levels"] == {"L1": 1, "L2": 1, "L3": 1, "UNKNOWN": 0}
    first = [chunk for chunk in chunks if chunk["document_id"] == "zakupki_kb:101"]
    assert len(first) == 1
    assert "Название: Как найти закупку?" in first[0]["text"]


def test_long_article_uses_existing_structured_chunker_deterministically():
    document = _ingested()[0][1]
    document["text"] = "\n".join(["Шаг процедуры содержит важное правило и пояснение."] * 20)
    first = chunk_knowledgebase_article(document, max_tokens=40)
    second = chunk_knowledgebase_article(document, max_tokens=40)
    assert len(first) > 1
    assert [chunk["chunk_id"] for chunk in first] == [chunk["chunk_id"] for chunk in second]
    assert all(chunk["title"] == document["title"] for chunk in first)


def test_html_cleaning_and_malformed_offline_payload(tmp_path):
    cleaned = clean_html_fragment("<p>Текст</p><ol><li>Первый</li></ol>")
    assert cleaned["text"] == "Текст\n- Первый"
    with pytest.raises(KnowledgeBaseAPIError):
        validate_payload({"not": "a list"})
    malformed = tmp_path / "bad.json"
    malformed.write_text("{bad", encoding="utf-8")
    with pytest.raises(KnowledgeBaseAPIError):
        load_payload(malformed)


def test_unknown_support_level_and_offline_payload_loading():
    assert classify_support_level("Справочник", "Общее описание раздела.") == "UNKNOWN"
    assert load_payload(FIXTURE)[0]["categoryId"] == 76000
