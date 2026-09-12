from src.application.knowledge_gap import knowledge_gap


def test_gap_detects_missing_knowledge_without_candidates():
    result = knowledge_gap(query="несуществующая функция", normalized_query="несуществующая функция",
                           status="ESCALATE_TO_OPERATOR", reason="no_relevant_evidence")
    assert result["detected"] is True
    assert result["classification"] == "NO_RELEVANT_DOCUMENTS"
    assert result["nearest_sources"] == []


def test_gap_detects_partial_knowledge_from_weak_official_evidence():
    candidate = {"chunk_id": "kb:1", "document_id": "kb", "title": "Related topic", "authority": "official",
                 "source_type": "official_kb", "raw_score": .4}
    result = knowledge_gap(query="detail", normalized_query="detail", status="ESCALATE_TO_OPERATOR",
                           reason="official_score_below_threshold", candidates=[candidate],
                           trace={"official_bm25": [candidate], "official_dense": [candidate]},
                           features={"top_score": .4, "retrieval_agreement": 1, "num_official_candidates": 1})
    assert result["detected"] is True
    assert result["classification"] == "PARTIAL_KNOWLEDGE"
    assert result["nearest_sources"][0]["chunk_id"] == "kb:1"


def test_answerable_and_ambiguous_queries_are_not_marked_as_knowledge_gaps():
    answer = knowledge_gap(query="known", normalized_query="known", status="ANSWER", reason=None)
    clarify = knowledge_gap(query="where?", normalized_query="where?", status="NEEDS_CLARIFICATION", reason=None)
    assert answer["detected"] is False
    assert clarify["detected"] is False
    assert clarify["classification"] == "AMBIGUOUS_QUERY"
