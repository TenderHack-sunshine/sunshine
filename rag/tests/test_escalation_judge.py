from src.application.escalation import EscalationJudge


def test_judge_keeps_an_incomplete_turn_in_the_dialog():
    decision = EscalationJudge().decide("выходит ошибка", "GENERATION_NOT_GROUNDED", [{}])
    assert decision.clarify is True
    assert decision.reason == "MISSING_ERROR_DETAILS"


def test_judge_escalates_a_non_mchd_follow_up():
    assert EscalationJudge().decide("а точнее", "GENERATION_NOT_GROUNDED", [{}]).clarify is False


def test_judge_escalates_a_concrete_unsupported_technical_problem():
    decision = EscalationJudge().decide("Ошибка 500 при подписании оферты", "no_relevant_evidence", [])
    assert decision.clarify is False
