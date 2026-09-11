from __future__ import annotations

import re


_REPLACEMENTS = {
    "м ч д": "мчд", "машино читаемая": "машиночитаемая", "личныйкабинет": "личный кабинет",
    "зарегестрир": "зарегистрир", "офферта": "оферта",
}


def normalize_query(text: str) -> str:
    """Conservative local typo/format normalization without rewriting user intent."""
    normalized = text.casefold().replace("ё", "е")
    normalized = re.sub(r"[^\w\s-]", " ", normalized, flags=re.UNICODE)
    normalized = " ".join(normalized.split())
    for source, replacement in _REPLACEMENTS.items():
        normalized = normalized.replace(source, replacement)
    return normalized
