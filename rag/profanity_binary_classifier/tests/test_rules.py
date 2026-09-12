from profanity_ml.rules import rule_probability


def test_rule_catches_spaced_obscenity():
    assert rule_probability("х у й сервис") == 1.0


def test_rule_catches_latin_mix():
    assert rule_probability("xуйня какая-то") == 1.0


def test_rule_keeps_non_obscene_complaint_clean():
    assert rule_probability("ужасный сервис, требую вернуть деньги") == 0.0
