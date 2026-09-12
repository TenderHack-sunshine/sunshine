from __future__ import annotations

import pytest

from src.core.config import Settings
from src.retrieval.mvp import rrf_fuse


def item(chunk_id: str, method: str) -> dict:
    return {"chunk_id": chunk_id, "document_id": chunk_id, "retrieval_method": method, "text": chunk_id}


def test_weighted_rrf_uses_rank_not_raw_scores():
    sparse = [item("sparse", "bm25"), item("shared", "bm25")]
    dense = [item("shared", "dense")]
    fused = rrf_fuse([sparse, dense], k=60, weights=[0.75, 1.5])
    by_id = {result["chunk_id"]: result for result in fused}
    assert by_id["sparse"]["rrf_score"] == pytest.approx(0.75 / 61)
    assert by_id["shared"]["rrf_score"] == pytest.approx(0.75 / 62 + 1.5 / 61)


def test_weighted_rrf_keeps_dense_only_result():
    result = rrf_fuse([[], [item("dense-only", "dense")]], weights=[0.5, 1.5])
    assert result[0]["chunk_id"] == "dense-only"
    assert result[0]["retrieval_method"] == "dense"
    assert result[0]["rrf_score"] == pytest.approx(1.5 / 61)


def test_weighted_rrf_keeps_bm25_only_result():
    result = rrf_fuse([[item("bm25-only", "bm25")], []], weights=[0.75, 1.0])
    assert result[0]["chunk_id"] == "bm25-only"
    assert result[0]["retrieval_method"] == "bm25"
    assert result[0]["rrf_score"] == pytest.approx(0.75 / 61)


def test_weighted_rrf_sums_result_present_in_both_lists():
    result = rrf_fuse([[item("shared", "bm25")], [item("shared", "dense")]], weights=[1.0, 1.25])
    assert result[0]["retrieval_method"] == "hybrid"
    assert result[0]["retrieval_methods"] == ["bm25", "dense"]
    assert result[0]["rrf_score"] == pytest.approx(2.25 / 61)


def test_default_equal_weight_behavior_is_preserved():
    lists = [[item("sparse", "bm25"), item("shared", "bm25")], [item("shared", "dense")]]
    assert rrf_fuse(lists) == rrf_fuse(lists, weights=[1.0, 1.0])


def test_dense_primary_is_the_default_retrieval_strategy():
    assert Settings().retrieval_strategy == "dense_primary"


def test_dense_weight_can_change_ranking():
    sparse = [item("sparse-first", "bm25")]
    dense = [item("dense-first", "dense")]
    equal = rrf_fuse([sparse, dense], weights=[1.0, 1.0])
    dense_biased = rrf_fuse([sparse, dense], weights=[1.0, 1.5])
    assert equal[0]["chunk_id"] == "sparse-first"
    assert dense_biased[0]["chunk_id"] == "dense-first"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [({"rrf_k": 0}, "RRF_K"), ({"dense_fusion_weight": -0.1}, "DENSE_FUSION_WEIGHT"), ({"dense_fusion_weight": 0, "bm25_fusion_weight": 0}, "At least one"), ({"retrieval_strategy": "unknown"}, "RETRIEVAL_STRATEGY")],
)
def test_invalid_fusion_configuration_fails_predictably(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Settings(**kwargs)


def test_invalid_rrf_arguments_fail_predictably():
    with pytest.raises(ValueError, match="positive"):
        rrf_fuse([], k=0)
    with pytest.raises(ValueError, match="one value"):
        rrf_fuse([[item("a", "bm25")]], weights=[1.0, 1.0])
    with pytest.raises(ValueError, match="non-negative"):
        rrf_fuse([[item("a", "bm25")]], weights=[-1.0])
