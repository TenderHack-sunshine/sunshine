import json
from pathlib import Path

from docx import Document
from openpyxl import Workbook

from scripts.ingest import _chunk_ticket, ingest_local_files
from src.ingestion.parsers.base import parse_file
from src.ingestion.parsers.pdf import repair_line_wraps


def test_xlsx_csv_text_markdown_and_json_parsers(tmp_path):
    workbook_path = tmp_path / "table.xlsx"
    workbook = Workbook()
    users = workbook.active
    users.title = "Users"
    users.append(["Role", "Permission"])
    users.append(["Supplier", "Submit application"])
    second = workbook.create_sheet("Other")
    second.append(["Name", "Value"])
    second.append(["Rule", "Required"])
    workbook.save(workbook_path)
    xlsx = parse_file(workbook_path)
    assert len(xlsx) == 2 and xlsx[0]["sheet"] == "Users" and "Role: Supplier" in xlsx[0]["text"]

    csv_path = tmp_path / "rows.csv"
    csv_path.write_bytes("Тема;Описание\nДоговор;Подписать\n".encode("cp1251"))
    csv_docs = parse_file(csv_path)
    assert csv_docs[0]["row"] == 2 and "Тема: Договор" in csv_docs[0]["text"]

    text_path = tmp_path / "note.txt"
    text_path.write_bytes("Первая строка\r\n\r\nВторая строка".encode("cp1251"))
    assert "Вторая строка" in parse_file(text_path)[0]["text"]

    markdown_path = tmp_path / "guide.md"
    markdown_path.write_text("# Заголовок\n- [Правило](https://example.test/rule)", encoding="utf-8")
    assert "# Заголовок" in parse_file(markdown_path)[0]["text"]

    json_path = tmp_path / "records.json"
    json_path.write_text(json.dumps([{"role": "supplier", "enabled": True}], ensure_ascii=False), encoding="utf-8")
    assert "role: supplier" in parse_file(json_path)[0]["text"]


def test_docx_tables_lists_and_pdf_line_repair(tmp_path):
    path = tmp_path / "guide.docx"
    document = Document()
    document.add_heading("Guide", level=1)
    document.add_paragraph("First step", style="List Bullet")
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Role", "Action"
    table.rows[1].cells[0].text, table.rows[1].cells[1].text = "Supplier", "Submit"
    document.save(path)
    parsed = parse_file(path)[0]["text"]
    assert "# Guide" in parsed and "- First step" in parsed and "Role: Supplier" in parsed
    assert repair_line_wraps("Поря-\nдок подачи") == "Порядок подачи"


def test_generic_ingestion_skips_knowledgebase_and_is_stable(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "one.txt").write_text(" ".join(["Useful local instruction with enough context."] * 12), encoding="utf-8")
    (raw / "ignored.bin").write_bytes(b"binary")
    (raw / "broken.json").write_text("{broken", encoding="utf-8")
    kb = raw / "zakupki_kb"
    kb.mkdir()
    (kb / "supplier.json").write_text("[]", encoding="utf-8")
    first_documents, first_chunks, report = ingest_local_files(raw)
    second_documents, second_chunks, second_report = ingest_local_files(raw)
    assert report["parsed_documents"] == 1 and report["unsupported_files"] == 1 and report["failed_files"] == 1
    assert first_documents[0]["source"] == "local_file"
    assert first_chunks[0]["document_id"] == first_documents[0]["document_id"]
    assert [item["document_id"] for item in first_documents] == [item["document_id"] for item in second_documents]
    assert [item["chunk_id"] for item in first_chunks] == [item["chunk_id"] for item in second_chunks]
    assert second_report["chunks"] == 1


def test_pdf_uses_one_document_id_and_global_chunk_ids(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    manual = raw / "manuals" / "guide.pdf"
    manual.parent.mkdir(parents=True)
    manual.write_bytes(b"pdf")
    pages = [
        {"text": " ".join(["first"] * 60), "source": "guide.pdf", "page": 1, "document_type": "manual"},
        {"text": " ".join(["second"] * 60), "source": "guide.pdf", "page": 2, "document_type": "manual"},
    ]
    monkeypatch.setattr("scripts.ingest.parse_file", lambda _: pages)
    documents, chunks, _ = ingest_local_files(raw)
    assert {document["document_id"] for document in documents} == {chunks[0]["document_id"]}
    assert [chunk["chunk_id"].rsplit(":", 1)[1] for chunk in chunks] == ["0", "1"]
    assert {chunk["source_type"] for chunk in chunks} == {"official_manual"}
    assert {chunk["authority"] for chunk in chunks} == {"official"}


def test_ticket_metadata_and_long_ticket_context(tmp_path):
    ticket = tmp_path / "Выгрузка СТП за 2026.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Влияние", "Заявитель", "Тема", "Статус", "Описание", "Решение"])
    sheet.append(["Высокое", "Пользователь", "Контракты", "Завершено", "Подтема запроса: Подписание/Не могу подписать", "Проверьте сертификат"])
    workbook.save(ticket)
    parsed = parse_file(ticket)[0]
    assert parsed["source_type"] == "support_ticket"
    assert parsed["subtopic"] == "Подписание"
    assert "Sheet:" not in parsed["text"] and "Проблема: Не могу подписать" in parsed["text"]
    long_ticket = {**parsed, "description": ". ".join(["Подробное описание проблемы содержит контекст" for _ in range(300)])}
    chunks = _chunk_ticket(long_ticket, 700, 1)
    assert len(chunks) > 1
    assert all(chunk["token_count"] <= 700 and chunk["text"].startswith("Тема: Контракты\nПодтема: Подписание") for chunk in chunks)
