from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class RetrievalResult:
    score: float
    text: str
    source: str
    page: int | None = None
    section: str | None = None
    authority: str = "manual"
    chunk_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
