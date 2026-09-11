from __future__ import annotations

from pathlib import Path
from typing import Any

from .chunker import chunk_documents
from .parsers import parse_directory
from src.core.config import Settings


def ingest_manuals(manuals_dir: str | Path, strategy: str | None = None, embedder: Any | None = None,
                   settings: Settings | None = None, **chunk_options: object) -> list[dict]:
    """Parse manuals into semantic chunks; recursive mode remains an explicit fallback."""
    settings = settings or Settings()
    chosen_strategy = strategy or ("semantic" if settings.semantic_chunking_enabled else "recursive")
    options = {
        "breakpoint_percentile": settings.semantic_breakpoint_percentile,
        "min_tokens": settings.min_chunk_tokens,
        "target_tokens": settings.target_chunk_tokens,
        "max_tokens": settings.max_chunk_tokens,
        "forced_split_overlap_tokens": settings.forced_split_overlap_tokens,
        **chunk_options,
    }
    if chosen_strategy == "semantic" and embedder is None:
        from src.retrieval.embedder import Embedder
        embedder = Embedder(settings.embedding_model_path)
    if chosen_strategy == "recursive":
        # Map semantic settings only when callers did not supply legacy values.
        options = {"chunk_size": options.pop("max_tokens"), "min_chunk_tokens": options.pop("min_tokens"), **options}
        options.pop("breakpoint_percentile", None)
        options.pop("target_tokens", None)
        options.pop("forced_split_overlap_tokens", None)
    return chunk_documents(parse_directory(manuals_dir), strategy=chosen_strategy, embedder=embedder, **options)
