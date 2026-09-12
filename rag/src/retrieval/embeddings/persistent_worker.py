"""Persistent local Qwen3 embedding worker with a tiny newline-delimited TCP protocol."""
from __future__ import annotations

import json
import socket
import socketserver
import threading
from time import perf_counter

from src.retrieval.embeddings.qwen3 import Qwen3Embedding


class PersistentEmbeddingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], model_path: str):
        load_started = perf_counter()
        self.embedder = Qwen3Embedding(model_path, batch_size=1)
        self.dimension = self.embedder.dimension
        self.model_load_ms = (perf_counter() - load_started) * 1000
        warmup_started = perf_counter()
        self.embedder.embed_query("warmup")
        self.warmup_ms = (perf_counter() - warmup_started) * 1000
        self.embedding_lock = threading.Lock()
        super().__init__(address, _EmbeddingRequestHandler)

    def response(self, request: dict) -> dict:
        operation = request.get("operation", "query")
        if operation == "status":
            return {"ok": True, "dimension": self.dimension, "device": self.embedder.device,
                    "dtype": self.embedder.precision, "model_load_ms": self.model_load_ms, "warmup_ms": self.warmup_ms}
        if operation != "query" or not isinstance(request.get("query"), str):
            raise ValueError("Only query embedding requests are supported")
        started = perf_counter()
        with self.embedding_lock:
            vector = self.embedder.embed_query(request["query"])
        return {"ok": True, "vector": vector.tolist(), "query_embedding_ms": (perf_counter() - started) * 1000}


class _EmbeddingRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline()
        try:
            response = self.server.response(json.loads(line.decode("utf-8")))  # type: ignore[attr-defined]
        except Exception as error:
            response = {"ok": False, "error": str(error)}
        self.wfile.write(json.dumps(response, ensure_ascii=True).encode("utf-8") + b"\n")


class PersistentQwenEmbeddingClient:
    """Small client; failure/timeout raises normal Python errors for BM25 fallback."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765, timeout_seconds: float = 12.0):
        self.host, self.port, self.timeout_seconds = host, port, timeout_seconds
        self.last_metrics: dict[str, float] = {}

    def _request(self, payload: dict, timeout: float | None = None) -> dict:
        with socket.create_connection((self.host, self.port), timeout=timeout or self.timeout_seconds) as connection:
            connection.settimeout(timeout or self.timeout_seconds)
            connection.sendall(json.dumps(payload, ensure_ascii=True).encode("utf-8") + b"\n")
            data = b""
            while not data.endswith(b"\n"):
                part = connection.recv(65536)
                if not part:
                    break
                data += part
        if not data:
            raise ConnectionError("embedding worker returned no response")
        response = json.loads(data.decode("utf-8"))
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "embedding worker failed"))
        return response

    def status(self, timeout_seconds: float = 0.5) -> dict:
        return self._request({"operation": "status"}, timeout=timeout_seconds)

    def embed_query(self, query: str) -> list[float]:
        response = self._request({"operation": "query", "query": query})
        self.last_metrics = {"query_embedding_ms": float(response.get("query_embedding_ms", 0.0))}
        return response["vector"]
