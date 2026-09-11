from __future__ import annotations

from .normalization import normalize_query


_TECHNICAL_MARKERS = (
    "ошиб", "не открыва", "не загружа", "не подписыва", "не работает", "сбой", "xml", "эдо",
    "код", "500", "403", "404", "техническ", "завис", "браузер",
)


class TechnicalRouter:
    """Transparent technical/non-technical gate for adding case-history evidence."""

    def classify(self, query: str) -> dict[str, object]:
        normalized = normalize_query(query)
        markers = [marker for marker in _TECHNICAL_MARKERS if marker in normalized]
        return {"intent": "technical" if markers else "non_technical", "technical": bool(markers), "markers": markers}
