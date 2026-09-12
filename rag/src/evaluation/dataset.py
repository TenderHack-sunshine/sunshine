from __future__ import annotations

import json
import shutil
from pathlib import Path


LABEL_FIELDS = ("relevant_chunk_ids", "relevant_document_ids", "notes")


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def save_jsonl_atomic(path: Path, rows: list[dict], backup: bool = True) -> None:
    if backup and path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    temporary.replace(path)


def candidate_ids(candidates: list[dict], positions: list[int]) -> tuple[list[str], list[str]]:
    selected = [candidates[position - 1] for position in positions if 1 <= position <= len(candidates)]
    return ([str(item["chunk_id"]) for item in selected if item.get("chunk_id")],
            [str(item["document_id"]) for item in selected if item.get("document_id")])


def apply_label(row: dict, candidates: list[dict], command: str) -> tuple[dict, str]:
    """Apply an explicit label command without touching non-label schema fields."""
    command = command.strip()
    if command in {"s", ""}:
        return row, "skipped"
    if command == "n":
        updated = dict(row)
        updated["relevant_chunk_ids"], updated["relevant_document_ids"] = [], []
        return updated, "none"
    if command.startswith("note "):
        updated = dict(row)
        updated["notes"] = command[5:].strip()
        return updated, "note"
    mode, values = "both", command
    if command[:2] in {"c ", "d ", "r "}:
        mode, values = {"c ": "chunk", "d ": "document", "r ": "replace"}[command[:2]], command[2:]
    try:
        positions = [int(value) for value in values.split()]
    except ValueError as error:
        raise ValueError("Use candidate positions, e.g. '1 3', 'c 1', 'd 2', 'r 1 3', 's' or 'n'") from error
    chunks, documents = candidate_ids(candidates, positions)
    updated = dict(row)
    if mode == "replace":
        updated["relevant_chunk_ids"], updated["relevant_document_ids"] = chunks, documents
    elif mode == "chunk":
        updated["relevant_chunk_ids"] = sorted(set(updated.get("relevant_chunk_ids", [])) | set(chunks))
    elif mode == "document":
        updated["relevant_document_ids"] = sorted(set(updated.get("relevant_document_ids", [])) | set(documents))
    else:
        updated["relevant_chunk_ids"] = sorted(set(updated.get("relevant_chunk_ids", [])) | set(chunks))
        updated["relevant_document_ids"] = sorted(set(updated.get("relevant_document_ids", [])) | set(documents))
    return updated, "labelled"
