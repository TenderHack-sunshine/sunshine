from __future__ import annotations

from pathlib import Path

from src.ingestion.chunker import approximate_token_count


class Embedder:
    """Lazy local embedding-model loader. It never downloads weights."""

    def __init__(self, model_path: str | Path, batch_size: int = 16):
        self.model_path = Path(model_path)
        self.batch_size = batch_size
        self._model = None
        self._tokenizer = None
        self._tokenizer_checked = False

    def _load(self):
        if self._model is None:
            if not self.model_path.exists():
                raise RuntimeError(f"Local embedding model not found: {self.model_path}")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(str(self.model_path), local_files_only=True)
        return self._model

    def embed_documents(self, texts: list[str]):
        return self._load().encode(texts, batch_size=self.batch_size, normalize_embeddings=True, show_progress_bar=False)

    def embed_query(self, query: str):
        return self._load().encode(query, normalize_embeddings=True)

    def count_tokens(self, text: str) -> int:
        """Use the local model tokenizer when possible; retain an offline fallback."""
        if not self._tokenizer_checked:
            self._tokenizer_checked = True
            try:
                from transformers import AutoTokenizer
                self._tokenizer = AutoTokenizer.from_pretrained(str(self.model_path), local_files_only=True)
            except Exception:
                self._tokenizer = None
        return len(self._tokenizer.encode(text, add_special_tokens=False)) if self._tokenizer else approximate_token_count(text)
