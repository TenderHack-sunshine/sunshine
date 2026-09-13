from src.application.clarification import ClarificationPolicy, clarification_question
from src.routing.intent import DomainLexicon, extract_intent_frame


def _lexicon():
    return DomainLexicon.from_chunks([
        {"title": "Электронный акт", "source_type": "official_manual"},
        {"title": "Котировочная сессия", "source_type": "official_manual"},
        {"title": "Реестр экспериментальных разрешений", "source_type": "official_manual"},
    ])


def test_generic_bare_topic_clarifies_the_missing_action():
    frame = extract_intent_frame("электронный акт", _lexicon())
    decision = ClarificationPolicy().evaluate(frame)
    assert decision.triggered
    assert decision.missing_slots == ("action",)
    assert clarification_question(frame).endswith("?")


def test_general_signature_problem_clarifies_object_and_error_details():
    frame = extract_intent_frame("Проблема с электронной подписью", _lexicon())
    decision = ClarificationPolicy().evaluate(frame)
    assert decision.triggered
    assert "object" in decision.missing_slots


def test_short_but_determinate_definition_does_not_clarify():
    frame = extract_intent_frame("Что такое котировочная сессия?", _lexicon())
    assert frame.intent == "definition"
    assert ClarificationPolicy().evaluate(frame).triggered is False


def test_new_object_uses_the_same_missing_slot_policy():
    frame = extract_intent_frame("Реестр экспериментальных разрешений", _lexicon())
    assert ClarificationPolicy().evaluate(frame).missing_slots == ("action",)
