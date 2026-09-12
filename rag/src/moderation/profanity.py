"""Deterministic, local-only Russian profanity matching.

Normalisation is used solely for matching. It never changes the user query that
is passed to the rest of the RAG pipeline.
"""
from __future__ import annotations

import re
import unicodedata


_HOMOGLYPHS = str.maketrans({
    "a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "u": "у", "x": "х", "y": "у",
    "A": "а", "C": "с", "E": "е", "O": "о", "P": "р", "U": "у", "X": "х", "Y": "у",
})
_SEPARATOR = r"[^а-яёa-z0-9]{0,3}"


# High-confidence obscene vocabulary only. In particular, there is no generic
# ``еб`` substring rule.
_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("exact", "хуй", re.compile(r"(?<![а-яё])х(?:" + _SEPARATOR + r"у{1,4}|[*#_.-]|\s)" + _SEPARATOR + r"[йи](?:ня|ло|[аяеиуы])?(?![а-яё])", re.IGNORECASE)),
    ("root", "хуй", re.compile(r"(?<![а-яё])ху(?:й|я|е|и|йня|ев|ило|есос)[а-яё]*(?![а-яё])", re.IGNORECASE)),
    ("exact", "пиздец", re.compile(r"(?<![а-яё])п" + _SEPARATOR + r"и?" + _SEPARATOR + r"з" + _SEPARATOR + r"д" + _SEPARATOR + r"е" + _SEPARATOR + r"ц(?![а-яё])", re.IGNORECASE)),
    ("root", "пизд", re.compile(r"(?<![а-яё])пизд(?:ец|а|ы|ой|еть|ить|юк)[а-яё]*(?![а-яё])", re.IGNORECASE)),
    ("exact", "блять", re.compile(r"(?<![а-яё])б" + _SEPARATOR + r"л" + _SEPARATOR + r"[я*#]" + _SEPARATOR + r"(?:т" + _SEPARATOR + r"ь|д" + _SEPARATOR + r"ь)(?![а-яё])", re.IGNORECASE)),
    ("root", "бля", re.compile(r"(?<![а-яё])бля(?:ть|дь|ха|ин|[еию])?(?![а-яё])", re.IGNORECASE)),
    ("exact", "ебать", re.compile(r"(?<![а-яё])[её]" + _SEPARATOR + r"б" + _SEPARATOR + r"а" + _SEPARATOR + r"т" + _SEPARATOR + r"ь(?![а-яё])", re.IGNORECASE)),
    ("root", "еб", re.compile(r"(?<![а-яё])(?:е|ё)б(?:ать|ал[аи]?|ан[а-яё]*|аш[а-яё]*|ись|нул[а-яё]*|нуть|твою)(?![а-яё])", re.IGNORECASE)),
    ("obfuscated", "ебать", re.compile(r"(?<![а-яё])е" + _SEPARATOR + r"(?:б|[*#])" + _SEPARATOR + r"ать(?![а-яё])", re.IGNORECASE)),
    ("root", "заеб", re.compile(r"(?<![а-яё])за(?:е|ё)б(?:ал|ать|ись|ешь|ут)[а-яё]*(?![а-яё])", re.IGNORECASE)),
    ("exact", "сука", re.compile(r"(?<![а-яё])сук(?:а|и|у|е|ой)(?![а-яё])", re.IGNORECASE)),
    ("obfuscated", "сука", re.compile(r"(?<![а-яё])с" + _SEPARATOR + r"(?:у|[*#])" + _SEPARATOR + r"ка(?![а-яё])", re.IGNORECASE)),
    ("exact", "мудак", re.compile(r"(?<![а-яё])муд(?:ак|ила|озвон)[а-яё]*(?![а-яё])", re.IGNORECASE)),
    ("obfuscated", "мудак", re.compile(r"(?<![а-яё])му" + _SEPARATOR + r"(?:д|[*#])" + _SEPARATOR + r"ак(?![а-яё])", re.IGNORECASE)),
)


def matching_representations(text: str) -> tuple[str, str]:
    """Return readable-normalized and separator-compacted representations."""
    normalized = unicodedata.normalize("NFKC", text).casefold().translate(_HOMOGLYPHS).replace("ё", "е")
    readable = re.sub(r"\s+", " ", normalized).strip()
    compact = re.sub(r"[\s_*#.-]+", "", readable)
    return readable, compact


def normalize_for_profanity(text: str) -> str:
    """Compatibility helper: return the compact matching representation."""
    return matching_representations(text)[1]


def detect_profanity(text: str) -> dict[str, object]:
    """Return deterministic match details without probabilistic semantics."""
    readable, compact = matching_representations(text)
    for match_type, canonical, pattern in _RULES:
        match = pattern.search(readable) or pattern.search(compact)
        if match:
            return {"contains_profanity": True, "matches": [canonical], "match_type": match_type,
                    "matched": match.group(0)}
    return {"contains_profanity": False, "matches": [], "match_type": None, "matched": None}
