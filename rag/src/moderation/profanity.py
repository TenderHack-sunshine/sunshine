from __future__ import annotations

import re

# Stems intentionally catch common Russian inflections but avoid sending text externally.
_STEMS = ("бляд", "бля", "хуй", "хуе", "пизд", "еба", "ёба", "заеб", "сук", "мудак", "гандон")
_SUBSTITUTIONS = str.maketrans({"@": "а", "4": "ч", "3": "з", "0": "о", "x": "х", "y": "у", "e": "е", "a": "а", "o": "о", "p": "р", "c": "с"})
_OBFUSCATED_PATTERNS = (("хуй", re.compile(r"х(?:[у*#][*#]?|[*#][у*#]?)[йи]")),)


def normalize_for_profanity(text: str) -> str:
    """Handle case, simple Latin/number substitutions, and punctuation obfuscation."""
    normalized = text.casefold().translate(_SUBSTITUTIONS)
    return re.sub(r"[^а-яё]+", "", normalized)


def detect_profanity(text: str) -> dict[str, object]:
    normalized = normalize_for_profanity(text)
    matches = [stem for stem in _STEMS if stem in normalized]
    compact_raw = re.sub(r"\s+", "", text.casefold().translate(_SUBSTITUTIONS))
    matches.extend(name for name, pattern in _OBFUSCATED_PATTERNS if pattern.search(compact_raw) and name not in matches)
    return {"contains_profanity": bool(matches), "matches": matches}
