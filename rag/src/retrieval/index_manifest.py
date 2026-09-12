"""Composition manifest for the official dense index."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def chunk_id_digest(chunks: list[dict]) -> str:
    value = "\n".join(sorted(str(chunk["chunk_id"]) for chunk in chunks))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_manifest(chunks: list[dict], collection: str) -> dict:
    return {"version": 1, "collection": collection, "official_chunk_count": len(chunks), "chunk_id_sha256": chunk_id_digest(chunks)}


def load_manifest(path: str | Path) -> dict | None:
    file_path = Path(path)
    try:
        value = json.loads(file_path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def manifest_matches(manifest: dict | None, chunks: list[dict], collection: str, point_count: int) -> bool:
    if not manifest or manifest.get("collection") != collection:
        return False
    expected = build_manifest(chunks, collection)
    return (
        manifest.get("official_chunk_count") == expected["official_chunk_count"] == point_count
        and manifest.get("chunk_id_sha256") == expected["chunk_id_sha256"]
    )
