"""Crash-isolated Qwen query adapter for the Windows CPU demonstration host."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


class IsolatedQwen3QueryEmbedding:
    """Run only query embedding in a Torch-only child process.

    The normal ``Qwen3Embedding`` remains the default reusable implementation.
    This adapter is selected by the CLI on the known Windows Torch/Qdrant native
    library conflict and makes timeout/failure a normal fallback condition.
    """

    def __init__(self, model_path: str | Path, timeout_seconds: float = 12.0):
        self.model_path = Path(model_path)
        self.timeout_seconds = timeout_seconds
        self.device = "cpu (isolated worker)"
        self.precision = "float32"

    def embed_query(self, query: str):
        request = json.dumps({"model_path": str(self.model_path), "query": query}, ensure_ascii=True).encode("utf-8")
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "src.retrieval.embeddings.qwen3_worker"],
                input=request, capture_output=True, timeout=self.timeout_seconds, check=True,
            )
        except subprocess.TimeoutExpired as error:
            raise TimeoutError(f"isolated Qwen query exceeded {self.timeout_seconds}s") from error
        except subprocess.CalledProcessError as error:
            detail = error.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"isolated Qwen query worker failed ({error.returncode}): {detail[-400:]}") from error
        response = json.loads(completed.stdout.decode("utf-8"))
        return response["vector"]


class IsolatedQwen3DocumentWorker:
    """Persistent Torch-only worker for the overnight REST indexer."""

    def __init__(self, model_path: str | Path):
        self.process = subprocess.Popen(
            [sys.executable, "-m", "src.retrieval.embeddings.qwen3_worker", "--serve", str(model_path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("isolated document worker streams are unavailable")
        self.process.stdin.write(json.dumps({"operation": "documents", "texts": texts}, ensure_ascii=True).encode("utf-8") + b"\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(f"isolated document worker exited with code {self.process.poll()}")
        return json.loads(line.decode("utf-8"))["vectors"]

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.stdin.close() if self.process.stdin else None
            self.process.terminate()
            self.process.wait(timeout=10)
