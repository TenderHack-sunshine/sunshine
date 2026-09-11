from __future__ import annotations

from pathlib import Path

from .base import clean_text, read_text_with_fallback


def parse_text(path: str | Path) -> list[dict]:
    path = Path(path)
    text = clean_text(read_text_with_fallback(path).replace("\r\n", "\n").replace("\r", "\n"))
    return [] if not text else [{
        "text": text, "source": path.name, "page": None, "document_type": "text",
        "source_type": "txt", "authority": "manual",
    }]
