from __future__ import annotations

import re
import unicodedata


LATIN_TO_CYRILLIC = str.maketrans(
    {
        "a": "а",
        "b": "б",
        "c": "с",
        "e": "е",
        "h": "н",
        "k": "к",
        "m": "м",
        "o": "о",
        "p": "р",
        "r": "г",
        "t": "т",
        "x": "х",
        "y": "у",
        "A": "а",
        "B": "в",
        "C": "с",
        "E": "е",
        "H": "н",
        "K": "к",
        "M": "м",
        "O": "о",
        "P": "р",
        "T": "т",
        "X": "х",
        "Y": "у",
    }
)

DIGIT_TO_CYRILLIC = str.maketrans(
    {
        "0": "о",
        "1": "и",
        "3": "з",
        "4": "ч",
        "6": "б",
        "8": "в",
        "@": "а",
        "$": "с",
    }
)

MASK_CHARS = "*#_!?.-+~="


def _squeeze_repeats(text: str) -> str:
    return re.sub(r"(.)\1{2,}", r"\1\1", text)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text))
    text = text.casefold().replace("ё", "е")
    text = text.translate(LATIN_TO_CYRILLIC).translate(DIGIT_TO_CYRILLIC)
    return _squeeze_repeats(text)


def compact_for_rules(text: str) -> str:
    normalized = normalize_text(text)
    keep_mask = re.escape(MASK_CHARS)
    return re.sub(fr"[^а-я{keep_mask}]+", "", normalized)


MASK = re.escape(MASK_CHARS)
W = fr"[{MASK}]*"
VOWEL_OR_MASK = fr"[аеёиоуыэюя{MASK}]"

PATTERNS: dict[str, re.Pattern[str]] = {
    "хуй": re.compile(fr"х+{W}у+{W}[йиеяю{MASK}]+"),
    "пизд": re.compile(fr"п+{W}и+{W}з+{W}д+"),
    "бляд": re.compile(fr"б+{W}л+{W}[я{MASK}]+{W}[дт{MASK}]+"),
    "ебать": re.compile(fr"(?<!тр)е+{W}б+{W}(а|и|у|н|л|т|уч|ан|ись|ись|ать)"),
    "ебан": re.compile(fr"е+{W}б+{W}а+{W}н+"),
    "ебуч": re.compile(fr"е+{W}б+{W}у+{W}ч+"),
    "заеб": re.compile(fr"з+{W}а+{W}е+{W}б+"),
    "уеб": re.compile(fr"у+{W}е+{W}б+"),
    "выеб": re.compile(fr"в+{W}ы+{W}е+{W}б+"),
    "мудак": re.compile(fr"м+{W}у+{W}д+{W}а+{W}к+"),
    "манда": re.compile(fr"м+{W}а+{W}н+{W}д+{VOWEL_OR_MASK}*"),
    "гандон": re.compile(fr"г+{W}а+{W}н+{W}д+{W}о+{W}н+"),
}


def rule_probability(text: str) -> float:
    normalized = compact_for_rules(text)
    return 1.0 if any(pattern.search(normalized) for pattern in PATTERNS.values()) else 0.0


def predict_rule_batch(texts: list[str]) -> list[float]:
    return [rule_probability(text) for text in texts]
