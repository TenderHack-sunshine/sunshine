from __future__ import annotations

from scripts.evaluate_retrieval import accuracy, grouped_metrics, markdown_report
from src.evaluation.dataset import apply_label


def _candidate(chunk_id="c", document_id="d"):
    return {"chunk_id": chunk_id, "document_id": document_id}


def test_labelling_adds_ids_without_overwriting_existing_labels():
    row = {"query": "q", "route": "L1", "relevant_chunk_ids": ["old"], "expected_decision": "ANSWER"}
    updated, outcome = apply_label(row, [_candidate()], "1")
    assert outcome == "labelled"
    assert updated["query"] == "q" and updated["route"] == "L1"
    assert set(updated["relevant_chunk_ids"]) == {"old", "c"}
    assert updated["relevant_document_ids"] == ["d"]


def test_labelling_skip_and_none_behaviour():
    row = {"query": "q", "relevant_chunk_ids": ["old"]}
    assert apply_label(row, [_candidate()], "s")[0] == row
    cleared, outcome = apply_label(row, [_candidate()], "n")
    assert outcome == "none"
    assert cleared["relevant_chunk_ids"] == [] and cleared["relevant_document_ids"] == []
    noted, outcome = apply_label(row, [_candidate()], "note review portal wording")
    assert outcome == "note" and noted["notes"] == "review portal wording"


def test_grouped_metrics_and_routing_decision_accuracy():
    case = {"category": "typo", "relevant_document_ids": ["d"]}
    grouped = grouped_metrics({"HYBRID": [(case, [_candidate(document_id="d")])]}, "category")
    assert grouped["typo"]["HYBRID"]["document"]["recall_at_1"] == 1.0
    report = accuracy([("L1", "L1"), ("L3", "L1")])
    assert report["accuracy"] == .5
    markdown = markdown_report({"metrics": {"HYBRID": {"chunk": {"recall_at_1": None, "recall_at_3": None, "recall_at_5": None, "recall_at_10": None, "mrr_at_10": None, "labelled_queries": 0}, "document": {"recall_at_1": 1., "recall_at_3": 1., "recall_at_5": 1., "recall_at_10": 1., "mrr_at_10": 1., "labelled_queries": 1}}}, "routing": {"accuracy": .5, "labelled_queries": 2}, "decisions": {"accuracy": None, "labelled_queries": 0}, "comparison": {}, "latency_ms": {}, "failure_analysis": []})
    assert "Tender Hack retrieval evaluation" in markdown
