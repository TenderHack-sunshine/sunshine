"""Long-lived deterministic runtime adapter for the profanity hard gate."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.moderation.profanity import detect_profanity


class ProfanityModelLoadError(RuntimeError):
    """Compatibility name retained for callers of the old adapter."""


@dataclass(frozen=True)
class ProfanityResult:
    detected: bool
    probability: float
    threshold: float
    match_type: str | None = None
    matched: str | None = None


class ProfanityDetector(Protocol):
    backend: str

    def detect(self, text: str) -> ProfanityResult: ...


class RuleProfanityDetector:
    """Compiled local rules; construction performs no model or file I/O."""

    backend = "rule"

    def detect(self, text: str) -> ProfanityResult:
        result = detect_profanity(text)
        detected = bool(result["contains_profanity"])
        return ProfanityResult(detected=detected, probability=1.0 if detected else 0.0, threshold=1.0,
                               match_type=result["match_type"], matched=result["matched"])


class MLProfanityDetector(RuleProfanityDetector):
    """Deprecated import-compatible name; no model is loaded anymore."""

    backend = "rule"

    def __init__(self, _model_dir: str | Path | None = None, _threshold_path: str | Path | None = None, **_kwargs):
        super().__init__()


def build_profanity_detector(backend: str = "rule", *_legacy_paths: str | Path) -> ProfanityDetector:
    normalized = backend.strip().lower()
    if normalized in {"rule", "deterministic"}:
        return RuleProfanityDetector()
    raise ValueError("PROFANITY_BACKEND must be rule or deterministic; ML profanity is retired")
