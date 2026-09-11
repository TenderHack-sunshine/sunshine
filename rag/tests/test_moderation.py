from src.moderation.profanity import detect_profanity


def test_profanity_detects_obfuscation():
    assert detect_profanity("Это х*йня")["contains_profanity"] is True
    assert detect_profanity("Нужна помощь с контрактом")["contains_profanity"] is False
