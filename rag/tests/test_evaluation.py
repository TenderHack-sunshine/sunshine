from __future__ import annotations

from scripts.evaluate_retrieval import metric_summary


def test_retrieval_metrics_for_known_ranking():
    case = {"relevant_chunk_ids": ["relevant"]}
    rankings = [(case, [{"chunk_id": "wrong"}, {"chunk_id": "relevant"}]), (case, [{"chunk_id": "relevant"}])]
    metrics = metric_summary(rankings)
    assert metrics["recall_at_1"] == .5
    assert metrics["recall_at_3"] == 1.0
    assert metrics["mrr_at_10"] == .75


def test_unlabelled_cases_do_not_create_fake_metrics():
    metrics = metric_summary([({"query": "unlabelled"}, [{"chunk_id": "x"}])])
    assert metrics["labelled_queries"] == 0
    assert metrics["recall_at_5"] is None
