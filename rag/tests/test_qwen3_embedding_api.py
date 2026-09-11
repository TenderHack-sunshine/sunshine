from __future__ import annotations

import numpy as np

from src.retrieval.embeddings.qwen3 import Qwen3Embedding


def test_qwen3_document_and_query_api_use_separate_formats(monkeypatch, tmp_path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    embedder = Qwen3Embedding(model_dir, device="cpu")
    calls = []

    def fake_encode(texts, *, prompt_name=None):
        calls.append((list(texts), prompt_name))
        return np.array([[1.0, 0.0] for _ in texts])

    monkeypatch.setattr(embedder, "_encode", fake_encode)
    assert embedder.embed_documents(["document"]).shape == (1, 2)
    assert embedder.embed_query("query").shape == (2,)
    assert calls == [(["document"], None), (["query"], "query")]
