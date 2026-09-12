from src.application.escalation import EscalationJudge


def test_judge_does_not_reinterpret_retrieval_failure_as_ambiguity():
    decision = EscalationJudge().decide("выходит ошибка", "GENERATION_NOT_GROUNDED", [{}])
    assert decision.clarify is False


def test_judge_escalates_a_non_mchd_follow_up():
    assert EscalationJudge().decide("а точнее", "GENERATION_NOT_GROUNDED", [{}]).clarify is False


def test_judge_escalates_a_concrete_unsupported_technical_problem():
    decision = EscalationJudge().decide("Ошибка 500 при подписании оферты", "no_relevant_evidence", [])
    assert decision.clarify is False
