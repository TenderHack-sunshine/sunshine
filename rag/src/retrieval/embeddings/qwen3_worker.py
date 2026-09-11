"""One-shot Qwen query worker used only on the Windows Intel demo machine.

It deliberately imports no Qdrant/HTTP modules: loading their native network
stack into the same Windows process as Torch causes an access violation here.
"""
from __future__ import annotations

import json
import sys

from src.retrieval.embeddings.qwen3 import Qwen3Embedding


def _response(embedder: Qwen3Embedding, request: dict) -> dict:
    if request.get("operation", "query") == "documents":
        vectors = embedder.embed_documents(request["texts"])
        return {"vectors": vectors.tolist(), "dimension": int(vectors.shape[1]), "device": embedder.device, "dtype": embedder.precision}
    vector = embedder.embed_query(request["query"])
    return {"vector": vector.tolist(), "dimension": int(vector.shape[0]), "device": embedder.device, "dtype": embedder.precision}


def main() -> None:
    if "--serve" in sys.argv:
        model_path = sys.argv[sys.argv.index("--serve") + 1]
        embedder = Qwen3Embedding(model_path, batch_size=1)
        for line in sys.stdin.buffer:
            request = json.loads(line.decode("utf-8"))
            sys.stdout.buffer.write(json.dumps(_response(embedder, request), ensure_ascii=True).encode("utf-8") + b"\n")
            sys.stdout.buffer.flush()
        return
    request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    embedder = Qwen3Embedding(request["model_path"], batch_size=1)
    sys.stdout.buffer.write(json.dumps(_response(embedder, request), ensure_ascii=True).encode("utf-8"))


if __name__ == "__main__":
    main()
