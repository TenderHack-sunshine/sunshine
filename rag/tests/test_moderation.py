from src.moderation.profanity import detect_profanity
import pytest


def test_profanity_detects_obfuscation():
    assert detect_profanity("Это х*йня")["contains_profanity"] is True
    assert detect_profanity("Нужна помощь с контрактом")["contains_profanity"] is False


@pytest.mark.parametrize("text", [
    "Это хуйня", "ХУЙ", "какого хуя", "пиздец", "блять", "ебать",
    "х*й", "х_й", "х-й", "х.й", "х у й", "xуй", "хуууй", "п*здец", "п и з д е ц", "бл*ть",
])
def test_rule_detector_catches_required_direct_and_obfuscated_forms(text):
    assert detect_profanity(text)["contains_profanity"] is True


@pytest.mark.parametrize("text", [
    "Как добавить МЧД?", "Не получается подписать документ", "Где найти закупку?", "Ошибка при загрузке файла",
    "Как изменить сертификат?", "Не могу загрузить XML", "суконная ткань", "мудрость пользователя", "пизанская башня",
])
def test_rule_detector_keeps_clean_support_and_tricky_negative_text_clean(text):
    assert detect_profanity(text)["contains_profanity"] is False
