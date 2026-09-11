from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Iterable


CANONICAL_FIELDS = (
    "chunk_id", "document_id", "text", "source_type", "authority", "support_level", "source_path",
    "title", "section", "page_start", "page_end", "metadata",
)


def _as_dict(value: object) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def canonicalize_chunk(chunk: dict, origin: str) -> dict:
    """Normalize one already-ingested chunk without changing its embedding text."""
    if not isinstance(chunk, dict):
        raise ValueError(f"{origin}: JSON value must be an object")
    chunk_id = str(chunk.get("chunk_id") or "")
    text = str(chunk.get("text") or "")
    if origin == "kb":
        source_type, authority = "official_kb", "official"
    else:
        source_type = str(chunk.get("source_type") or "local_file")
        authority = str(chunk.get("authority") or "unknown")

    metadata = _as_dict(chunk.get("metadata"))
    known = set(CANONICAL_FIELDS)
    for key, value in chunk.items():
        if key not in known and key not in metadata:
            metadata[key] = value

    # KB exports keep useful fields both at top level and inside metadata across versions.
    def value(name: str):
        return chunk.get(name) if chunk.get(name) is not None else metadata.get(name)

    title = value("title")
    source_path = chunk.get("source_path") or value("source_path")
    page_start = chunk.get("page_start")
    page_end = chunk.get("page_end")
    if page_start is None:
        page_start = chunk.get("page")
    if page_end is None:
        page_end = page_start
    support_level = value("support_level")
    canonical = {
        "chunk_id": chunk_id,
        "document_id": str(chunk.get("document_id") or chunk_id.rsplit(":", 1)[0]),
        "text": text,
        "source_type": source_type,
        "authority": authority,
        "support_level": support_level,
        "source_path": source_path,
        "title": title,
        "section": chunk.get("section"),
        "page_start": page_start,
        "page_end": page_end,
        "metadata": metadata,
    }
    return canonical


def read_jsonl(path: str | Path) -> Iterable[dict]:
    path = Path(path)
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                raise ValueError(f"{path}:{line_number}: empty JSONL line")
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: malformed JSON: {error.msg}") from error
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: JSON value must be an object")
            yield value


def _percentile(values: list[int], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def validate_canonical_chunks(chunks: list[dict], kb_count: int, local_count: int) -> dict:
    ids = [chunk["chunk_id"] for chunk in chunks]
    duplicates = sorted(chunk_id for chunk_id, count in Counter(ids).items() if count > 1)
    empty_text = sum(not chunk["text"].strip() for chunk in chunks)
    if duplicates:
        raise ValueError(f"Duplicate chunk_id values ({len(duplicates)}): {duplicates[:5]}")
    if empty_text:
        raise ValueError(f"Canonical chunks with empty text: {empty_text}")
    token_counts = [int(chunk.get("metadata", {}).get("token_count", 0) or 0) for chunk in chunks]
    return {
        "kb_chunks": kb_count,
        "local_chunks": local_count,
        "total_canonical_chunks": len(chunks),
        "unique_chunk_ids": len(set(ids)),
        "duplicate_chunk_ids": 0,
        "empty_text_count": 0,
        "source_type_distribution": dict(sorted(Counter(chunk["source_type"] for chunk in chunks).items())),
        "authority_distribution": dict(sorted(Counter(chunk["authority"] for chunk in chunks).items())),
        "support_level_distribution": dict(sorted(Counter(str(chunk["support_level"]) if chunk["support_level"] is not None else "null" for chunk in chunks).items())),
        "token_statistics": {
            "min": min(token_counts, default=0), "median": median(token_counts) if token_counts else 0,
            "mean": mean(token_counts) if token_counts else 0, "p95": _percentile(token_counts, .95), "max": max(token_counts, default=0),
        },
    }


def prepare_canonical_chunks(kb_path: str | Path, local_path: str | Path) -> tuple[list[dict], dict]:
    kb_chunks = [canonicalize_chunk(chunk, "kb") for chunk in read_jsonl(kb_path)]
    local_chunks = [canonicalize_chunk(chunk, "local") for chunk in read_jsonl(local_path)]
    chunks = kb_chunks + local_chunks
    return chunks, validate_canonical_chunks(chunks, len(kb_chunks), len(local_chunks))


def write_jsonl(path: str | Path, records: Iterable[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
