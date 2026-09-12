from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExperimentConfig:
    data_path: Path
    output_dir: Path
    seed: int = 42
    max_length: int = 256
    stride: int = 64
    learning_rate: float = 2e-5
    batch_size_gpu: int = 32
    batch_size_cpu: int = 8
    epochs: int = 5
    min_epochs: int = 3
    weight_decay: float = 0.01
    early_stopping_patience: int = 2
    target_recall: float = 0.95
    fine_tune_model_name: str = "cointegrated/rubert-tiny2"
    toxicity_model_name: str = "cointegrated/rubert-tiny-toxicity"


def load_config(path: str | Path) -> ExperimentConfig:
    config_path = Path(path).resolve()
    with config_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    base_dir = config_path.parent
    data_path = Path(raw["data_path"])
    output_dir = Path(raw["output_dir"])
    if not data_path.is_absolute():
        data_path = (base_dir / data_path).resolve()
    if not output_dir.is_absolute():
        output_dir = (base_dir.parent / output_dir).resolve()

    values = dict(raw)
    values["data_path"] = data_path
    values["output_dir"] = output_dir
    return ExperimentConfig(**values)
