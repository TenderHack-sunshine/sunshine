from __future__ import annotations

import numpy as np

from src.retrieval.vector_store import HttpQdrantStore, QdrantStore


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


def test_local_http_store_uses_numeric_loopback_socket(monkeypatch):
    calls = []

    class Connection:
        def __init__(self):
            self.read = False

        def settimeout(self, timeout):
            calls.append(("timeout", timeout))

        def connect(self, address):
            calls.append(("connect", address))

        def sendall(self, payload):
            calls.append(("request", payload))

        def recv(self, _size):
            if self.read:
                return b""
            self.read = True
            return b'HTTP/1.1 200 OK\r\nContent-Length: 33\r\n\r\n{"result":{"exists":true}}'

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr("src.retrieval.vector_store.socket.socket", lambda *_args: Connection())
    store = HttpQdrantStore(host="localhost", port=6333, collection="official")
    assert store.collection_exists() is True
    assert ("connect", ("127.0.0.1", 6333)) in calls
    assert any(item[0] == "request" and item[1].startswith(b"GET /collections/official/exists HTTP/1.1") for item in calls)
