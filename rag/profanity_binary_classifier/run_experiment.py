from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from profanity_ml.config import load_config
from profanity_ml.data import load_dataset, split_dataset, validate_dataset
from profanity_ml.metrics import (
    compute_metrics,
    flatten_metrics_for_table,
    save_error_examples,
    timed_predict,
)
from profanity_ml.rules import predict_rule_batch
from profanity_ml.threshold import choose_threshold
from profanity_ml.training import train_fine_tuned_model
from profanity_ml.transformer_inference import (
    get_device,
    load_sequence_classifier,
    predict_transformer_sliding,
)


def _evaluate_probabilities(
    system: str,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    val_probs: np.ndarray,
    test_probs: np.ndarray,
    validation_seconds: float,
    test_seconds: float,
    target_recall: float,
    output_dir: Path,
) -> dict[str, object]:
    threshold = choose_threshold(
        validation_df["label"].to_numpy(dtype=int),
        val_probs,
        target_recall=target_recall,
    )
    validation_metrics = compute_metrics(validation_df, val_probs, threshold.threshold)
    test_metrics = compute_metrics(test_df, test_probs, threshold.threshold)
    system_dir = output_dir / system
    error_files = {
        "validation": save_error_examples(
            validation_df, val_probs, threshold.threshold, system_dir, "validation"
        ),
        "test": save_error_examples(test_df, test_probs, threshold.threshold, system_dir, "test"),
    }
    return {
        "system": system,
        "threshold": threshold.__dict__,
        "validation": validation_metrics,
        "test": test_metrics,
        "validation_inference_seconds": validation_seconds,
        "test_inference_seconds": test_seconds,
        "error_files": error_files,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/default.json")
    parser.add_argument("--skip-training", action="store_true")
    parser.add_argument("--skip-toxicity", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    df = load_dataset(config.data_path)
    validation_report = validate_dataset(df)
    train_df, validation_df, test_df = split_dataset(df)

    report: dict[str, object] = {
        "data_validation": asdict(validation_report),
        "config": {
            "seed": config.seed,
            "max_length": config.max_length,
            "stride": config.stride,
            "learning_rate": config.learning_rate,
            "batch_size_gpu": config.batch_size_gpu,
            "batch_size_cpu": config.batch_size_cpu,
            "epochs": config.epochs,
            "min_epochs": config.min_epochs,
            "weight_decay": config.weight_decay,
            "target_recall": config.target_recall,
        },
        "systems": {},
    }

    val_probs, val_time = timed_predict("rule", validation_df, predict_rule_batch)
    test_probs, test_time = timed_predict("rule", test_df, predict_rule_batch)
    report["systems"]["rule_based"] = _evaluate_probabilities(
        "rule_based",
        validation_df,
        test_df,
        val_probs,
        test_probs,
        val_time,
        test_time,
        config.target_recall,
        config.output_dir,
    )

    device = get_device()
    batch_size = config.batch_size_gpu if device.type == "cuda" else config.batch_size_cpu

    if not args.skip_toxicity:
        tokenizer, model = load_sequence_classifier(config.toxicity_model_name, device=device)
        predictor = lambda texts: predict_transformer_sliding(
            texts,
            tokenizer,
            model,
            max_length=config.max_length,
            stride=config.stride,
            batch_size=batch_size,
            probability_mode="toxicity_obscenity",
        )
        val_probs, val_time = timed_predict("toxicity", validation_df, predictor)
        test_probs, test_time = timed_predict("toxicity", test_df, predictor)
        report["systems"]["rubert_tiny_toxicity"] = _evaluate_probabilities(
            "rubert_tiny_toxicity",
            validation_df,
            test_df,
            val_probs,
            test_probs,
            val_time,
            test_time,
            config.target_recall,
            config.output_dir,
        )

    if not args.skip_training:
        report["fine_tuning"] = train_fine_tuned_model(
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

    fine_tuned_dir = config.output_dir / "fine_tuned_rubert_tiny2" / "best_model"
    if fine_tuned_dir.exists():
        tokenizer, model = load_sequence_classifier(str(fine_tuned_dir), device=device)
        predictor = lambda texts: predict_transformer_sliding(
            texts,
            tokenizer,
            model,
            max_length=config.max_length,
            stride=config.stride,
            batch_size=batch_size,
            probability_mode="binary",
        )
        val_probs, val_time = timed_predict("fine_tuned", validation_df, predictor)
        test_probs, test_time = timed_predict("fine_tuned", test_df, predictor)
        report["systems"]["fine_tuned_rubert_tiny2"] = _evaluate_probabilities(
            "fine_tuned_rubert_tiny2",
            validation_df,
            test_df,
            val_probs,
            test_probs,
            val_time,
            test_time,
            config.target_recall,
            config.output_dir,
        )

    rows = []
    for name, item in report["systems"].items():
        rows.append(
            flatten_metrics_for_table(
                name,
                "test",
                item["test"],
                item["test_inference_seconds"],
            )
        )
    comparison = pd.DataFrame(rows)
    report["comparison_table_test"] = comparison.to_dict(orient="records")
    comparison.to_csv(config.output_dir / "comparison_table_test.csv", index=False, encoding="utf-8-sig")
    (config.output_dir / "experiment_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
