from src.moderation.profanity import detect_profanity
import pytest


def test_profanity_detects_obfuscation():
    assert detect_profanity("Это х*йня")["contains_profanity"] is True
    assert detect_profanity("Нужна помощь с контрактом")["contains_profanity"] is False


@pytest.mark.parametrize("text", [
    "\u043d\u0430\u0445\u0443\u0439", "\u043f\u043e\u0445\u0443\u0439", "\u043d\u0438\u0445\u0443\u044f", "\u043e\u0445\u0443\u0435\u0442\u044c", "\u043e\u0445\u0443\u0435\u043d\u043d\u043e",
    "\u0434\u043e\u0435\u0431\u0430\u0442\u044c\u0441\u044f", "\u043f\u0440\u043e\u0435\u0431\u0430\u043b", "\u043d\u0430\u0435\u0431\u0430\u043b", "\u0443\u0435\u0431\u043e\u043a", "\u0434\u043e\u043b\u0431\u043e\u0451\u0431",
    "\u043d \u0430 \u0445 \u0443 \u0439", "\u043d\u0430*\u0443\u0439", "x\u0443\u0439", "\u043f*\u0437\u0434\u0435\u0446", "\u0431\u043b*\u0442\u044c", "\u0435*\u0430\u0442\u044c",
])
def test_profanity_detects_realistic_prefixed_and_obfuscated_variants(text):
    assert detect_profanity(text)["contains_profanity"] is True


@pytest.mark.parametrize("text", ["\u043f\u043e\u0445\u0443\u0434\u0435\u0442\u044c", "\u043c\u0430\u0442\u0435\u0440\u0438\u0430\u043b", "XML \u0444\u0430\u0439\u043b \u043d\u0435 \u0437\u0430\u0433\u0440\u0443\u0436\u0430\u0435\u0442\u0441\u044f"])
def test_profanity_prefix_rules_keep_clean_words_clean(text):
    assert detect_profanity(text)["contains_profanity"] is False


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
