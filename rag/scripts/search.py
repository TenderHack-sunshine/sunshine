from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import Settings
from src.retrieval.dense import DenseRetriever
from src.retrieval.embeddings.qwen3 import Qwen3Embedding
from src.retrieval.vector_store import QdrantStore


def _preview(text: str, length: int = 280) -> str:
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= length else normalized[:length - 1] + "…"


def main() -> None:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Dense Qwen3 + Qdrant search; no reranking and no generation.")
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--collection", default=settings.qdrant_collection)
    parser.add_argument("--source-type", action="append")
    parser.add_argument("--authority", action="append")
    parser.add_argument("--support-level", action="append")
    parser.add_argument("--max-per-document", type=int, default=2)
    parser.add_argument("--host", default=settings.qdrant_host)
    parser.add_argument("--port", type=int, default=settings.qdrant_port)
    args = parser.parse_args()
    filters = {key: value for key, value in {
        "source_type": args.source_type, "authority": args.authority, "support_level": args.support_level,
    }.items() if value}
    retriever = DenseRetriever(
        Qwen3Embedding(settings.embedding_model_path), QdrantStore(args.host, args.port, args.collection), args.max_per_document,
    )
    for rank, result in enumerate(retriever.retrieve(args.query, args.top_k, filters or None), start=1):
        location = result.get("title") or result.get("source_path") or "unknown"
        page = result.get("page_start")
        print(f"#{rank} score={result['score']:.4f}")
        print(f"source={result.get('source_type')} authority={result.get('authority')} support_level={result.get('support_level')}")
        print(f"file={location}" + (f" page={page}" if page is not None else ""))
        print(f"text={_preview(result.get('text', ''))}")
        print(f"chunk_id={result.get('chunk_id')}\n")


if __name__ == "__main__":
    main()
