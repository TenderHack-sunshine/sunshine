from __future__ import annotations

import numpy as np

from src.retrieval.dense import DenseRetriever
from src.retrieval.vector_store import payload_for_chunk, point_id_for_chunk
from scripts.index_qdrant import length_aware_batches


class FakeEmbedder:
    def embed_query(self, query):
        return np.array([1.0, 0.0])


class FakeStore:
    def __init__(self, results):
        self.results = results
        self.filters = None

    def search(self, vector, limit, filters=None):
        self.filters = filters
        return self.results[:limit]


def test_point_id_and_payload_are_deterministic_and_complete():
    chunk = {"chunk_id": "local:abc:0", "page_start": 3, "metadata": {"topic": "MCHD"}}
    assert point_id_for_chunk(chunk["chunk_id"]) == point_id_for_chunk(chunk["chunk_id"])
    payload = payload_for_chunk(chunk)
    assert payload["page"] == 3
    assert payload["metadata"]["topic"] == "MCHD"


def test_dense_retriever_filters_and_limits_one_document():
    store = FakeStore([
        {"chunk_id": "a:0", "document_id": "a", "score": .9},
        {"chunk_id": "a:1", "document_id": "a", "score": .8},
        {"chunk_id": "b:0", "document_id": "b", "score": .7},
    ])
    results = DenseRetriever(FakeEmbedder(), store, max_per_document=1).retrieve(
        "query", top_k=2, filters={"authority": "official"},
    )
    assert [item["chunk_id"] for item in results] == ["a:0", "b:0"]
    assert store.filters == {"authority": "official"}


def test_length_aware_batches_keep_all_chunks_and_group_small_first():
    chunks = [
        {"chunk_id": "c", "metadata": {"token_count": 50}},
        {"chunk_id": "a", "metadata": {"token_count": 2}},
        {"chunk_id": "b", "metadata": {"token_count": 10}},
    ]
    assert [[item["chunk_id"] for item in batch] for batch in length_aware_batches(chunks, 2)] == [["a", "b"], ["c"]]
