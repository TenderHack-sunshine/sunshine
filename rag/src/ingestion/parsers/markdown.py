from __future__ import annotations

import re
from pathlib import Path

from .base import clean_text, read_text_with_fallback


def parse_markdown(path: str | Path) -> list[dict]:
    path = Path(path)
    raw = read_text_with_fallback(path).replace("\r\n", "\n")
    raw = re.sub(r"!?(\[[^\]]*\])\(([^)]+)\)", r"\1 (\2)", raw)
    text = clean_text(raw)
    return [] if not text else [{
        "text": text, "source": path.name, "page": None, "document_type": "markdown",
        "source_type": "markdown", "authority": "manual",
    }]
