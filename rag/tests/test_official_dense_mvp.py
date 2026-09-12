from __future__ import annotations

import json
import threading
import time

from scripts.index_official_qdrant import OFFICIAL_SOURCE_TYPES, index_resumable, select_official_chunks
from src.retrieval.mvp import TwoPathRetriever
from src.retrieval.official_dense import DenseUnavailable, OfficialDenseRetriever
from src.retrieval.vector_store import HttpQdrantStore


def _chunk(chunk_id: str, text: str, source_type: str, authority: str, document_id: str | None = None) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": document_id or chunk_id,
        "text": text,
        "source_type": source_type,
        "authority": authority,
        "support_level": "L1",
        "title": "Source",
        "source_path": "source.pdf",
        "section": "Section",
        "page_start": 1,
        "page_end": 1,
        "metadata": {"topic": "topic", "subtopic": "subtopic"},
    }


class _Dense:
    def __init__(self, result: list[dict] | None = None, error: Exception | None = None):
        self.result = result or []
        self.error = error
        self.last_timing = {"query_embedding_ms": 2.0, "dense_search_ms": 3.0}

    def retrieve(self, *_args, **_kwargs):
        if self.error:
            raise self.error
        return self.result


def _dense_result(chunk: dict) -> dict:
    return {
        **chunk,
        "retrieval_method": "dense",
        "raw_score": 0.99,
        "rank": 1,
    }


def test_official_selection_excludes_all_tickets():
    official = _chunk("official", "create offer", "official_manual", "official")
    ticket = _chunk("ticket", "offer error", "support_ticket", "case_history")
    selected = select_official_chunks([official, ticket])
    assert [item["chunk_id"] for item in selected] == ["official"]
    assert all(item["source_type"] in OFFICIAL_SOURCE_TYPES for item in selected)
    assert all(item["source_type"] != "support_ticket" for item in selected)


def test_official_index_is_idempotent_and_has_no_ticket_vectors(tmp_path):
    class FakeWorker:
        @staticmethod
        def embed_documents(texts):
            return [[1.0] * 1024 for _ in texts]

    class FakeStore:
        collection = "official"

        def __init__(self):
            self.points = {}

        def create_collection(self, _dimension, recreate=False):
            if recreate:
                self.points = {}

        def count(self):
            return len(self.points)

        def upsert(self, chunks, _vectors):
            self.points.update({chunk["chunk_id"]: chunk for chunk in chunks})
            return len(chunks)

    official = select_official_chunks([
        _chunk("o1", "manual one", "official_manual", "official"),
        _chunk("o2", "taxonomy", "support_taxonomy", "taxonomy"),
        _chunk("t1", "ticket", "support_ticket", "case_history"),
    ])
    input_path = tmp_path / "chunks.jsonl"
    input_path.write_text("\n".join(json.dumps(item) for item in official), encoding="utf-8")
    store = FakeStore()
    checkpoint = tmp_path / "checkpoint.json"
    first = index_resumable(input_path=input_path, store=store, worker=FakeWorker(), checkpoint_path=checkpoint, recreate=True, log_every=1)
    second = index_resumable(input_path=input_path, store=store, worker=FakeWorker(), checkpoint_path=checkpoint, recreate=False, log_every=1)
    assert first["qdrant_points"] == 2
    assert second["qdrant_points"] == 2
    assert set(store.points) == {"o1", "o2"}


def test_technical_query_fuses_dense_official_and_ticket_bm25_with_schema_and_timing():
    official = _chunk("official", "offer guide", "official_manual", "official")
    ticket = _chunk("ticket", "offer error resolution", "support_ticket", "case_history")
    retriever = TwoPathRetriever.from_canonical([official, ticket], official_dense=_Dense([_dense_result(official)]), retrieval_strategy="hybrid_rrf")
    trace = retriever.retrieve_with_trace("offer error", technical=True, top_k=5)
    assert trace["dense_available"] is True
    assert trace["fallback_used"] is False
    assert trace["retrieval_mode"] == "HYBRID"
    assert trace["official_dense"][0]["retrieval_method"] == "dense"
    assert trace["ticket_bm25"][0]["retrieval_method"] == "bm25"
    assert {item["source_type"] for item in trace["results"]} == {"official_manual", "support_ticket"}
    assert all({"chunk_id", "document_id", "text", "source_type", "authority", "retrieval_method", "raw_score", "rank", "metadata", "rrf_score"} <= set(item) for item in trace["results"])
    assert set(trace["timing"]) >= {"query_embedding_ms", "dense_search_ms", "bm25_ms", "fusion_ms", "total_retrieval_ms"}


def test_official_bm25_and_dense_duplicate_is_one_hybrid_rrf_result():
    official = _chunk("official", "offer guide", "official_manual", "official")
    retriever = TwoPathRetriever.from_canonical([official], official_dense=_Dense([_dense_result(official)]), retrieval_strategy="hybrid_rrf")
    trace = retriever.retrieve_with_trace("offer", technical=False, top_k=5)
    assert trace["dense_available"] is True
    assert trace["retrieval_mode"] == "HYBRID"
    assert len(trace["results"]) == 1
    assert trace["results"][0]["retrieval_method"] == "hybrid"
    assert trace["results"][0]["retrieval_methods"] == ["bm25", "dense"]


def test_dense_primary_is_default_and_keeps_strong_dense_result_first():
    dense_chunk = _chunk("dense", "unrelated manual", "official_manual", "official")
    sparse_chunk = _chunk("sparse", "create offer procedure", "official_kb", "official")
    retriever = TwoPathRetriever.from_canonical([dense_chunk, sparse_chunk], official_dense=_Dense([_dense_result(dense_chunk)]))
    trace = retriever.retrieve_with_trace("create offer", technical=False, top_k=5)
    assert trace["retrieval_strategy"] == "DENSE_PRIMARY"
    assert trace["retrieval_mode"] == "DENSE_PRIMARY"
    assert trace["dense_primary_used"] is True
    assert trace["bm25_rescue_used"] is False
    assert trace["results"][0]["chunk_id"] == "dense"


def test_dense_primary_adds_sparse_rescue_when_dense_evidence_is_weak():
    dense_chunk = _chunk("dense", "unrelated manual", "official_manual", "official")
    sparse_chunk = _chunk("sparse", "create offer procedure", "official_kb", "official")
    weak_dense = {**_dense_result(dense_chunk), "raw_score": .1, "score": .1}
    retriever = TwoPathRetriever.from_canonical([dense_chunk, sparse_chunk], official_dense=_Dense([weak_dense]))
    trace = retriever.retrieve_with_trace("create offer", technical=False, top_k=5)
    assert trace["retrieval_mode"] == "DENSE_PRIMARY_RESCUE"
    assert trace["bm25_rescue_used"] is True
    assert [item["chunk_id"] for item in trace["results"][:2]] == ["dense", "sparse"]


def test_dense_timeout_keeps_official_bm25_fallback_mode():
    official = _chunk("official", "create offer guide", "official_manual", "official")
    retriever = TwoPathRetriever.from_canonical([official], official_dense=_Dense(error=DenseUnavailable("timeout")))
    trace = retriever.retrieve_with_trace("create offer", technical=False)
    assert trace["dense_available"] is False
    assert trace["fallback_used"] is True
    assert trace["retrieval_mode"] == "BM25_FALLBACK"
    assert trace["bm25_fallback_used"] is True


def test_dense_embedding_or_qdrant_failure_uses_official_bm25_fallback():
    official = _chunk("official", "create offer guide", "official_manual", "official")
    retriever = TwoPathRetriever.from_canonical([official], official_dense=_Dense(error=DenseUnavailable("embedding failed")))
    trace = retriever.retrieve_with_trace("create offer", technical=False)
    assert trace["dense_available"] is False
    assert trace["fallback_used"] is True
    assert trace["dense_error"] == "embedding failed"
    assert trace["official_fallback"][0]["chunk_id"] == "official"


def test_official_dense_rejects_ticket_payload_even_if_store_is_misconfigured():
    class Embedder:
        @staticmethod
        def embed_query(_query):
            return [1.0, 0.0]

    class Store:
        @staticmethod
        def search(*_args, **_kwargs):
            return [_chunk("ticket", "leak", "support_ticket", "case_history")]

    result = OfficialDenseRetriever(Embedder(), Store()).retrieve("query")
    assert result == []


def test_dense_timeout_does_not_accumulate_non_daemon_executor_threads():
    release = threading.Event()

    class SlowEmbedder:
        @staticmethod
        def embed_query(_query):
            release.wait(1)
            return [1.0, 0.0]

    class Store:
        @staticmethod
        def search(*_args, **_kwargs):
            return []

    retriever = OfficialDenseRetriever(SlowEmbedder(), Store(), query_timeout_seconds=.01)
    try:
        try:
            retriever.retrieve("first")
        except DenseUnavailable as error:
            assert "timed out" in str(error)
        try:
            retriever.retrieve("second")
        except DenseUnavailable as error:
            assert "in progress" in str(error)
    finally:
        release.set()
        time.sleep(.01)


def test_rest_qdrant_payload_mapping_uses_stable_payload_and_filters(monkeypatch):
    store = HttpQdrantStore(collection="official")
    calls = []

    def request(method, path, body=None):
        calls.append((method, path, body))
        if path.endswith("/exists"):
            return {"result": {"exists": False}}
        if path.endswith("/points/count"):
            return {"result": {"count": 1}}
        if path.endswith("/points/query"):
            return {"result": {"points": [{"score": .9, "payload": _chunk("o", "guide", "official_kb", "official")} ]}}
        return {"result": True}

    monkeypatch.setattr(store, "_request", request)
    chunk = _chunk("o", "guide", "official_kb", "official")
    store.create_collection(1024)
    store.upsert([chunk], [[1.0] * 1024])
    result = store.search([1.0] * 1024, filters={"source_type": ["official_kb"]})
    assert result[0]["metadata"]["topic"] == "topic"
    upsert = next(body for method, path, body in calls if method == "PUT" and path.startswith("/collections/official/points"))
    assert upsert["points"][0]["payload"]["document_id"] == "o"
    query = next(body for method, path, body in calls if path.endswith("/points/query"))
    assert query["filter"]["must"][0]["match"] == {"any": ["official_kb"]}
