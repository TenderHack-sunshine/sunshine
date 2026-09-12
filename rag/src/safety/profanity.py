"""Long-lived runtime adapters for the local profanity classifiers."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.moderation.profanity import detect_profanity


class ProfanityModelLoadError(RuntimeError):
    """The explicitly configured ML safety gate could not start."""


@dataclass(frozen=True)
class ProfanityResult:
    detected: bool
    probability: float
    threshold: float


class ProfanityDetector(Protocol):
    backend: str

    def detect(self, text: str) -> ProfanityResult: ...


def _inference_utilities(classifier_src: Path):
    """Import the existing classifier inference functions without a subprocess."""
    source = str(classifier_src)
    if source not in sys.path:
        sys.path.insert(0, source)
    try:
        from profanity_ml.transformer_inference import (  # type: ignore[import-not-found]
            get_device,
            load_sequence_classifier,
            predict_transformer_sliding,
        )
    except Exception as error:  # pragma: no cover - depends on optional ML installation.
        raise ProfanityModelLoadError(
            f"Could not import profanity classifier inference utilities from {classifier_src}: {error}"
        ) from error
    return get_device, load_sequence_classifier, predict_transformer_sliding


class MLProfanityDetector:
    """Loads the fine-tuned rubert-tiny2 model and threshold exactly once."""

    backend = "ml"

    def __init__(self, model_dir: str | Path, threshold_path: str | Path, *, classifier_src: str | Path | None = None,
                 max_length: int = 256, stride: int = 64, batch_size_cpu: int = 8, batch_size_gpu: int = 32):
        self.model_dir = Path(model_dir).resolve()
        self.threshold_path = Path(threshold_path).resolve()
        if not self.model_dir.is_dir():
            raise ProfanityModelLoadError(f"Configured profanity model directory does not exist: {self.model_dir}")
        if not self.threshold_path.is_file():
            raise ProfanityModelLoadError(f"Configured profanity threshold file does not exist: {self.threshold_path}")
        try:
            payload = json.loads(self.threshold_path.read_text(encoding="utf-8"))
            self.threshold = float(payload["threshold"])
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ProfanityModelLoadError(f"Invalid profanity threshold file {self.threshold_path}: {error}") from error
        if not 0.0 <= self.threshold <= 1.0:
            raise ProfanityModelLoadError(f"Profanity threshold must be in [0, 1], got {self.threshold}")

        source = Path(classifier_src) if classifier_src else Path(__file__).resolve().parents[2] / "profanity_binary_classifier" / "src"
        get_device, load_sequence_classifier, predict_transformer_sliding = _inference_utilities(source.resolve())
        try:
            self.device = get_device()
            self.tokenizer, self.model = load_sequence_classifier(str(self.model_dir), device=self.device)
        except Exception as error:
            raise ProfanityModelLoadError(f"Could not load profanity model from {self.model_dir}: {error}") from error
        self._predict = predict_transformer_sliding
        self.max_length = max_length
        self.stride = stride
        self.batch_size = batch_size_gpu if getattr(self.device, "type", "cpu") == "cuda" else batch_size_cpu

    def detect(self, text: str) -> ProfanityResult:
        probability = float(self._predict(
            [text], self.tokenizer, self.model, max_length=self.max_length, stride=self.stride,
            batch_size=self.batch_size, probability_mode="binary",
        )[0])
        return ProfanityResult(detected=probability >= self.threshold, probability=probability, threshold=self.threshold)


class RuleProfanityDetector:
    """Explicit compatibility backend; it is never an implicit ML fallback."""

    backend = "rule"

    def detect(self, text: str) -> ProfanityResult:
        detected = bool(detect_profanity(text)["contains_profanity"])
        return ProfanityResult(detected=detected, probability=1.0 if detected else 0.0, threshold=1.0)


def build_profanity_detector(backend: str, model_dir: str | Path, threshold_path: str | Path) -> ProfanityDetector:
    normalized = backend.strip().lower()
    if normalized == "ml":
        return MLProfanityDetector(model_dir, threshold_path)
    if normalized == "rule":
        return RuleProfanityDetector()
    raise ValueError("PROFANITY_BACKEND must be ml or rule")
