from __future__ import annotations

import threading

from src.retrieval.embeddings import persistent_worker


def test_persistent_worker_loads_model_once_and_serves_multiple_queries(monkeypatch):
    loads = []

    class FakeQwen:
        device = "cpu"
        precision = "float32"

        def __init__(self, *_args, **_kwargs):
            loads.append(1)

        @property
        def dimension(self):
            return 2

        @staticmethod
        def embed_query(_query):
            return type("Vector", (), {"tolist": lambda self: [1.0, 0.0]})()

    monkeypatch.setattr(persistent_worker, "Qwen3Embedding", FakeQwen)
    server = persistent_worker.PersistentEmbeddingServer(("127.0.0.1", 0), "unused")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = persistent_worker.PersistentQwenEmbeddingClient("127.0.0.1", server.server_address[1], 1)
        assert client.status()["dimension"] == 2
        assert client.embed_query("one") == [1.0, 0.0]
        assert client.embed_query("two") == [1.0, 0.0]
        assert len(loads) == 1
    finally:
        server.shutdown()
        server.server_close()
