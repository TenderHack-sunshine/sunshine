from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import clean_text


def _to_text(value: Any, depth: int = 0) -> str:
    if depth > 3:
        return ""
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "; ".join(part for item in value for part in [_to_text(item, depth + 1)] if part)
    if isinstance(value, dict):
        return "\n".join(f"{key}: {text}" for key, item in value.items() if (text := _to_text(item, depth + 1)))
    return ""


def parse_json(path: str | Path) -> list[dict]:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload if isinstance(payload, list) else [payload]
    documents = []
    for index, record in enumerate(records):
        text = _to_text(record)
        if text:
            documents.append({
                "text": text, "source": path.name, "page": None, "record": index,
                "document_type": "json_record", "source_type": "json", "authority": "manual",
            })
    return documents
