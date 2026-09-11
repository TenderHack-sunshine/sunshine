from __future__ import annotations

from pathlib import Path
from time import perf_counter
from collections.abc import Callable
from typing import Iterable


class Qwen3Embedding:
    """Local Qwen3-Embedding component with the model's native query prompt."""

    def __init__(self, model_path: str | Path, batch_size: int = 16, device: str | None = None):
        self.model_path = Path(model_path)
        self.batch_size = batch_size
        self.device = device or self.select_device()
        # AVX2 CPUs generally execute this transformer faster and with a lower
        # peak allocation in float32 than emulated float16. CUDA selects its
        # own efficient kernels through SentenceTransformers.
        self.precision = "float32"
        self._model = None
        self._dimension: int | None = None

    @staticmethod
    def select_device() -> str:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _load(self):
        if self._model is None:
            if not self.model_path.is_dir():
                raise RuntimeError(f"Local Qwen3 embedding model not found: {self.model_path}")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                str(self.model_path), device=self.device, local_files_only=True,
            )
            dimension_getter = getattr(self._model, "get_embedding_dimension", self._model.get_sentence_embedding_dimension)
            self._dimension = int(dimension_getter())
        return self._model

    @property
    def dimension(self) -> int:
        self._load()
        assert self._dimension is not None
        return self._dimension

    def _encode(self, texts: Iterable[str], *, prompt_name: str | None = None):
        items = list(texts)
        if not items:
            return []
        import torch

        arguments = {
            "batch_size": self.batch_size,
            "normalize_embeddings": True,
            "show_progress_bar": False,
            "convert_to_numpy": True,
        }
        if prompt_name:
            arguments["prompt_name"] = prompt_name
        with torch.inference_mode():
            return self._load().encode(items, **arguments)

    def embed_documents(self, texts: Iterable[str], progress_callback: Callable[[int, int], None] | None = None):
        """Documents use plain text, as prescribed by Qwen3-Embedding."""
        import numpy as np

        items = list(texts)
        batches = []
        for start in range(0, len(items), self.batch_size):
            batches.append(self._encode(items[start:start + self.batch_size]))
            if progress_callback:
                progress_callback(min(start + self.batch_size, len(items)), len(items))
        return np.concatenate(batches, axis=0) if batches else np.empty((0, self.dimension), dtype=np.float32)

    def embed_query(self, query: str):
        """Queries use the model-provided ``query`` prompt, not an invented prompt."""
        vectors = self._encode([query], prompt_name="query")
        return vectors[0]

    def benchmark(self, texts: list[str], progress_callback: Callable[[int, int], None] | None = None) -> dict:
        """Embed a small sample and validate dimensionality, norms and determinism."""
        if not texts:
            raise ValueError("Cannot benchmark an empty sample")
        import numpy as np

        started = perf_counter()
        vectors = self.embed_documents(texts, progress_callback=progress_callback)
        elapsed = perf_counter() - started
        matrix = np.asarray(vectors, dtype=np.float32)
        duplicate = self.embed_documents([texts[0], texts[0]])
        norms = np.linalg.norm(matrix, axis=1)
        return {
            "device": self.device,
            "precision": self.precision,
            "embedding_dimension": int(matrix.shape[1]),
            "batch_size": self.batch_size,
            "chunks": len(texts),
            "elapsed_seconds": elapsed,
            "chunks_per_second": len(texts) / elapsed if elapsed else 0.0,
            "has_nan_or_inf": not bool(np.isfinite(matrix).all()),
            "consistent_dimension": bool(matrix.ndim == 2 and matrix.shape[1] == self.dimension),
            "norm_min": float(norms.min()), "norm_mean": float(norms.mean()), "norm_max": float(norms.max()),
            "deterministic_same_text": bool(np.allclose(duplicate[0], duplicate[1], rtol=1e-5, atol=1e-6)),
        }
