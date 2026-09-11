from __future__ import annotations

"""Resumable overnight official-only Qdrant REST indexer (never indexes tickets)."""

import argparse
import json
import sys
from itertools import islice
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.core.config import Settings
from src.retrieval.canonical import read_jsonl
from src.retrieval.embeddings.isolated_qwen3 import IsolatedQwen3DocumentWorker
from src.retrieval.official_dense import OfficialDenseRetriever
from src.retrieval.vector_store import HttpQdrantStore

OFFICIAL_SOURCE_TYPES = frozenset(OfficialDenseRetriever.official_source_types)
VECTOR_DIMENSION = 1024


def iter_official_chunks(path: Path):
    for chunk in read_jsonl(path):
        if chunk.get("source_type") in OFFICIAL_SOURCE_TYPES:
            yield chunk


def select_official_chunks(chunks: list[dict]) -> list[dict]:
    """Testable filter; the real indexer streams through ``iter_official_chunks``."""
    selected = [chunk for chunk in chunks if chunk.get("source_type") in OFFICIAL_SOURCE_TYPES]
    if not selected:
        raise ValueError("No official chunks found")
    assert all(chunk["source_type"] != "support_ticket" for chunk in selected)
    return selected


def _batches(items, size: int):
    iterator = iter(items)
    while batch := list(islice(iterator, size)):
        yield batch


def load_checkpoint(path: Path, collection: str, existing_points: int) -> set[str]:
    if not path.exists():
        return set()
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        completed = set(saved.get("completed_chunk_ids", []))
        return completed if saved.get("collection") == collection and existing_points >= len(completed) else set()
    except (OSError, json.JSONDecodeError):
        return set()


def save_checkpoint(path: Path, collection: str, completed: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"collection": collection, "completed_chunk_ids": sorted(completed)}, ensure_ascii=True), encoding="utf-8")
    temporary.replace(path)


def index_resumable(*, input_path: Path, store, worker, checkpoint_path: Path, batch_size: int = 1,
                    recreate: bool = False, log_every: int = 25, emit=print) -> dict:
    """Stream official chunks, upsert stable UUID points, then checkpoint each batch."""
    total = sum(1 for _ in iter_official_chunks(input_path))
    if not total:
        raise ValueError("No official chunks selected")
    store.create_collection(VECTOR_DIMENSION, recreate=recreate)
    existing = store.count()
    completed = set() if recreate else load_checkpoint(checkpoint_path, store.collection, existing)
    if recreate:
        save_checkpoint(checkpoint_path, store.collection, completed)
    started = perf_counter()
    starting_completed = len(completed)
    processed = len(completed)
    last_log = processed
    for batch in _batches((item for item in iter_official_chunks(input_path) if item["chunk_id"] not in completed), batch_size):
        batch_started = perf_counter()
        vectors = worker.embed_documents([item["text"] for item in batch])
        if len(vectors) != len(batch) or any(len(vector) != VECTOR_DIMENSION for vector in vectors):
            raise RuntimeError("Qwen worker returned an invalid vector batch")
        store.upsert(batch, vectors)
        completed.update(item["chunk_id"] for item in batch)
        save_checkpoint(checkpoint_path, store.collection, completed)
        processed = len(completed)
        if processed - last_log >= log_every or processed == total:
            elapsed = perf_counter() - started
            rate = (processed - starting_completed) / elapsed if elapsed else 0.0
            eta = (total - processed) / rate if rate else 0.0
            emit(f"[{processed}/{total}] elapsed={elapsed:.1f}s eta={eta:.1f}s rate={rate:.3f} chunks/s last_batch={perf_counter() - batch_started:.1f}s qdrant_points={store.count()}", flush=True)
            last_log = processed
    return {"official_chunks": total, "completed_chunks": len(completed), "qdrant_points": store.count(), "checkpoint": str(checkpoint_path)}


def main() -> None:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Run overnight official-only Qwen/Qdrant REST indexing; tickets are never selected.")
    parser.add_argument("--input", type=Path, default=settings.processed_dir / "index" / "all_chunks.jsonl")
    parser.add_argument("--collection", default=settings.qdrant_official_collection)
    parser.add_argument("--checkpoint", type=Path, default=settings.processed_dir / "index" / "official_index_checkpoint.json")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--log-every", type=int, default=25)
    parser.add_argument("--recreate", action="store_true", help="Intentionally discard the collection and start a new checkpoint.")
    args = parser.parse_args()
    if args.batch_size < 1 or args.log_every < 1:
        parser.error("--batch-size and --log-every must be positive")
    store = HttpQdrantStore(settings.qdrant_host, settings.qdrant_port, args.collection)
    worker = IsolatedQwen3DocumentWorker(settings.embedding_model_path)
    try:
        report = index_resumable(input_path=args.input, store=store, worker=worker, checkpoint_path=args.checkpoint,
                                 batch_size=args.batch_size, recreate=args.recreate, log_every=args.log_every)
    finally:
        worker.close()
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
