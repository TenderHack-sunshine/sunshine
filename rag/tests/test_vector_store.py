from __future__ import annotations

import numpy as np

from src.retrieval.vector_store import QdrantStore


def test_qdrant_store_upsert_filter_and_idempotency(tmp_path):
    store = QdrantStore(collection="canonical", local_path=tmp_path / "qdrant")
    store.create_collection(vector_size=2)
    chunks = [
        {"chunk_id": "a", "document_id": "doc-a", "text": "official", "authority": "official", "source_type": "official_kb", "metadata": {"article_id": 1}},
        {"chunk_id": "b", "document_id": "doc-b", "text": "ticket", "authority": "case_history", "source_type": "support_ticket", "metadata": {}},
    ]
    vectors = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    assert store.upsert(chunks, vectors) == 2
    assert store.upsert(chunks, vectors) == 2
    assert store.count() == 2
    result = store.search(np.array([1.0, 0.0]), filters={"authority": "official"})
    assert [item["chunk_id"] for item in result] == ["a"]
    assert result[0]["metadata"]["article_id"] == 1
