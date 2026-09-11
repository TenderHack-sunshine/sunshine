from __future__ import annotations

import argparse
import json
import sys
from itertools import islice
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import Settings
from src.retrieval.canonical import read_jsonl
from src.retrieval.embeddings.qwen3 import Qwen3Embedding
from src.retrieval.vector_store import QdrantStore


def _validate_benchmark(report: dict) -> None:
    if report["has_nan_or_inf"] or not report["consistent_dimension"] or not report["deterministic_same_text"]:
        raise RuntimeError(f"Embedding smoke validation failed: {report}")
    if not .98 <= report["norm_mean"] <= 1.02:
        raise RuntimeError(f"Normalized embedding norms are unexpected: {report['norm_mean']}")


def _token_count(chunk: dict) -> int:
    return int((chunk.get("metadata") or {}).get("token_count") or 0)


def length_aware_batches(chunks: list[dict], batch_size: int):
    """Group similarly sized chunks so CPU/GPU padding does not dominate inference."""
    ordered = sorted(chunks, key=lambda chunk: (_token_count(chunk), chunk["chunk_id"]))
    for start in range(0, len(ordered), batch_size):
        yield ordered[start:start + batch_size]


def _batches(records, batch_size: int):
    iterator = iter(records)
    while batch := list(islice(iterator, batch_size)):
        yield sorted(batch, key=lambda chunk: (_token_count(chunk), chunk["chunk_id"]))


def _count_records(path: Path) -> int:
    return sum(1 for _ in read_jsonl(path))


def main() -> None:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Embed the canonical corpus with local Qwen3 and upsert it into one Qdrant collection.")
    parser.add_argument("--input", type=Path, default=settings.processed_dir / "index" / "all_chunks.jsonl")
    parser.add_argument("--collection", default=settings.qdrant_collection)
    parser.add_argument("--batch-size", type=int, default=1, help="Embedding batch size; CPU default is conservative for Qwen3 memory.")
    parser.add_argument("--upsert-batch-size", type=int, default=64)
    parser.add_argument("--limit", type=int, help="Index only the first N chunks; use for a smoke run.")
    parser.add_argument("--smoke-size", type=int, default=100, help="Sample size benchmarked before any upserts.")
    parser.add_argument("--recreate", action="store_true", help="Intentionally replace an existing collection.")
    parser.add_argument("--host", default=settings.qdrant_host)
    parser.add_argument("--port", type=int, default=settings.qdrant_port)
    args = parser.parse_args()
    if args.batch_size <= 0 or args.upsert_batch_size <= 0 or args.smoke_size <= 0:
        parser.error("batch sizes and --smoke-size must be positive")

    total = _count_records(args.input)
    selected_total = min(total, args.limit) if args.limit is not None else total
    if not selected_total:
        raise SystemExit("No canonical chunks selected for indexing")
    smoke_chunks = list(islice(read_jsonl(args.input), min(args.smoke_size, selected_total)))
    embedder = Qwen3Embedding(settings.embedding_model_path, batch_size=args.batch_size)
    smoke = embedder.benchmark(
        [chunk["text"] for chunk in smoke_chunks],
        progress_callback=lambda completed, total: print(f"[smoke {completed}/{total}]"),
    )
    _validate_benchmark(smoke)
    estimate = (selected_total / smoke["chunks_per_second"]) if smoke["chunks_per_second"] else None
    print(json.dumps({"embedding_smoke": smoke, "estimated_embedding_seconds": estimate}, ensure_ascii=True, indent=2))

    store = QdrantStore(args.host, args.port, args.collection)
    store.create_collection(embedder.dimension, recreate=args.recreate)
    started = perf_counter()
    indexed = 0
    records = read_jsonl(args.input)
    if args.limit is not None:
        records = islice(records, args.limit)
    for batch_number, batch in enumerate(_batches(records, args.upsert_batch_size), start=1):
        vectors = embedder.embed_documents([chunk["text"] for chunk in batch])
        indexed += store.upsert(batch, vectors, batch_size=args.upsert_batch_size)
        elapsed = perf_counter() - started
        rate = indexed / elapsed if elapsed else 0.0
        remaining = (selected_total - indexed) / rate if rate else 0.0
        print(f"[batch={batch_number} {indexed}/{selected_total}] elapsed={elapsed:.1f}s rate={rate:.2f} chunks/s eta={remaining:.1f}s")
    report = {
        "collection": args.collection, "indexed_chunks": indexed, "collection_points": store.count(),
        "embedding_model_path": str(settings.embedding_model_path), "device": embedder.device,
        "precision": embedder.precision, "embedding_dimension": embedder.dimension, "batch_size": args.batch_size,
        "elapsed_seconds": perf_counter() - started,
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
