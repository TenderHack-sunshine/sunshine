from __future__ import annotations

from scripts.run_e2e_demo_eval import evaluate_scenario, source_review


def _result(*, status="ANSWER", sources=None, **diagnostics):
    return {
        "route": "L1", "status": status, "answer": "answer", "sources": sources or [],
        "diagnostics": {"retrieval_strategy": "DENSE_PRIMARY", "retrieval_mode": "DENSE_PRIMARY", "dense_available": True,
                        "dense_primary_used": True, "bm25_rescue_used": False, "bm25_fallback_used": False,
                        "profanity_detected": False, "clarification_policy_triggered": False, "clarification_reason": "NONE",
                        "timings_ms": {}, **diagnostics},
    }


def _official():
    return {"chunk_id": "official", "document_id": "official", "source_type": "official_manual", "authority": "official", "title": "Guide"}


def test_answer_requires_manual_review_even_when_structural_expectations_pass():
    scenario = {"id": "answer", "query": "query", "expected_route": "L1", "expected_decision": "ANSWER", "expected_retrieval": "DENSE_PRIMARY", "requires_official_evidence": True}
    row = evaluate_scenario(scenario, _result(sources=[_official()]), 10.0)
    assert row["structural_result"] == "PASS"
    assert row["result"] == "REVIEW"
    assert row["grounding_warnings"] == []


def test_answer_without_official_evidence_is_visible_as_warning_and_failure_when_required():
    scenario = {"id": "unsafe", "query": "query", "expected_decision": "ANSWER", "requires_official_evidence": True}
    row = evaluate_scenario(scenario, _result(sources=[{"chunk_id": "ticket", "source_type": "support_ticket", "authority": "case_history"}]), 10.0)
    assert "ANSWER_ZERO_OFFICIAL_EVIDENCE" in row["grounding_warnings"]
    assert "Official evidence was required but absent" in row["expectation_mismatches"]
    assert row["result"] == "FAIL"


def test_evidence_hierarchy_flags_ticket_before_official():
    evidence, warnings = source_review(_result(sources=[{"chunk_id": "ticket", "source_type": "support_ticket", "authority": "case_history"}, _official()]))
    assert len(evidence) == 2
    assert warnings == ["TICKET_PRECEDES_OFFICIAL_EVIDENCE"]
