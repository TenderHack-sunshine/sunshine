from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import Settings
from src.ingestion.tickets import tickets_to_chunks
from src.retrieval.embedder import Embedder
from src.retrieval.vector_store import QdrantStore


def main() -> None:
    settings = Settings()
    chunks_file = settings.processed_dir / "manual_chunks.jsonl"
    if not chunks_file.exists():
        raise SystemExit(f"Run scripts/ingest_documents.py first; not found: {chunks_file}")
    chunks = [json.loads(line) for line in chunks_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    tickets_file = settings.processed_dir / "tickets.jsonl"
    if tickets_file.exists():
        tickets = [json.loads(line) for line in tickets_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        chunks.extend(tickets_to_chunks(tickets))
    if not chunks:
        raise SystemExit("No chunks to index")
    vectors = Embedder(settings.embedding_model_path).embed_documents([chunk["text"] for chunk in chunks])
    store = QdrantStore(settings.qdrant_host, settings.qdrant_port, settings.qdrant_collection)
    store.create_collection(vector_size=len(vectors[0]), recreate=True)
    store.upsert(chunks, vectors)
    print(f"Indexed {len(chunks)} chunks in local Qdrant collection {settings.qdrant_collection!r}")


if __name__ == "__main__":
    main()
