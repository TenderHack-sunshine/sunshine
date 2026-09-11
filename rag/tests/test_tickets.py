import pandas as pd

from src.ingestion.tickets import extract_question, load_taxonomy, preprocess_tickets


def test_question_extraction():
    assert extract_question("Подтема запроса: Подписание контракта/Не могу подписать контракт") == ("Подписание контракта", "Не могу подписать контракт")


def test_taxonomy_and_tickets(tmp_path):
    taxonomy_file = tmp_path / "taxonomy.xlsx"
    tickets_file = tmp_path / "tickets.xlsx"
    pd.DataFrame({"Тема": ["Контракты"], "Подтема": ["Подписание"]}).to_excel(taxonomy_file, index=False)
    pd.DataFrame({"Тема": ["Контракты"], "Описание": ["Подтема запроса: Подписание/ Не могу подписать"], "Решение": ["Инструкция отправлена"], "Статус": ["Закрыто"]}).to_excel(tickets_file, index=False)
    records = preprocess_tickets(tickets_file, load_taxonomy(taxonomy_file))
    assert records[0]["taxonomy_recognized"] is True
    assert records[0]["question"] == "Не могу подписать"
    assert records[0]["authority"] == "historical_ticket"
