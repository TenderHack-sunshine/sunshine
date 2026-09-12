from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from profanity_ml.config import load_config
from profanity_ml.data import load_dataset, split_dataset, validate_dataset
from profanity_ml.training import train_fine_tuned_model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/default.json")
    args = parser.parse_args()

    config = load_config(args.config)
    df = load_dataset(config.data_path)
    validate_dataset(df)
    train_df, validation_df, _ = split_dataset(df)

    summary = train_fine_tuned_model(
        train_df=train_df,
        validation_df=validation_df,
        model_name=config.fine_tune_model_name,
        output_dir=config.output_dir / "fine_tuned_rubert_tiny2",
        seed=config.seed,
        max_length=config.max_length,
        stride=config.stride,
        learning_rate=config.learning_rate,
        batch_size_gpu=config.batch_size_gpu,
        batch_size_cpu=config.batch_size_cpu,
        epochs=config.epochs,
        min_epochs=config.min_epochs,
        weight_decay=config.weight_decay,
        early_stopping_patience=config.early_stopping_patience,
        target_recall=config.target_recall,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
