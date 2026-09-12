from src.application.evidence_frames import compatibility, frame_evidence
from src.routing.intent import DomainLexicon, extract_intent_frame


def _lexicon():
    return DomainLexicon.from_chunks([
        {"title": "Реестр экспериментальных разрешений", "source_type": "official_manual"},
        {"title": "Электронное актирование", "source_type": "official_manual"},
    ])


def test_intent_frame_uses_a_new_corpus_object_not_a_subject_rule():
    frame = extract_intent_frame("Как подписать реестр экспериментальных разрешений", _lexicon())
    assert frame.intent == "how_to"
    assert frame.object == "реестр экспериментальных разрешений"
    assert frame.action == "sign"
    assert frame.missing_slots == ()


def test_bare_corpus_object_requires_an_action_not_more_keywords():
    frame = extract_intent_frame("Реестр экспериментальных разрешений", _lexicon())
    assert frame.intent == "unknown"
    assert frame.missing_slots == ("action",)


def test_evidence_action_mismatch_is_rejected_for_any_object():
    lexicon = _lexicon()
    intent = extract_intent_frame("Как подписать реестр экспериментальных разрешений", lexicon)
    evidence = frame_evidence({
        "title": "Как заменить реестр экспериментальных разрешений",
        "text": "Чтобы заменить запись, откройте карточку и выберите изменение.",
        "authority": "official",
    }, lexicon)
    assert compatibility(intent, evidence) == (False, "ACTION_MISMATCH")


def test_troubleshooting_without_object_clarifies_missing_context():
    frame = extract_intent_frame("выходит ошибка", _lexicon())
    assert frame.intent == "troubleshooting"
    assert "object" in frame.missing_slots
