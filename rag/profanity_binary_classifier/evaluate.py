from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from profanity_ml.config import load_config
from profanity_ml.data import load_dataset, split_dataset, validate_dataset
from profanity_ml.metrics import compute_metrics, save_error_examples, timed_predict
from profanity_ml.rules import predict_rule_batch
from profanity_ml.threshold import choose_threshold
from profanity_ml.transformer_inference import (
    get_device,
    load_sequence_classifier,
    predict_transformer_sliding,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/default.json")
    parser.add_argument("--system", choices=["rule", "toxicity", "finetuned"], required=True)
    parser.add_argument("--model-dir", default=None)
    parser.add_argument("--split", choices=["validation", "test"], default="test")
    args = parser.parse_args()

    config = load_config(args.config)
    df = load_dataset(config.data_path)
    validate_dataset(df)
    _, validation_df, test_df = split_dataset(df)
    eval_df = validation_df if args.split == "validation" else test_df

    if args.system == "rule":
        val_probs, _ = timed_predict("rule", validation_df, predict_rule_batch)
        threshold_info = choose_threshold(
            validation_df["label"].to_numpy(dtype=int),
            val_probs,
            target_recall=config.target_recall,
        )
        probs, elapsed = timed_predict("rule", eval_df, predict_rule_batch)
    else:
        model_path = args.model_dir
        probability_mode = "binary"
        if args.system == "toxicity":
            model_path = model_path or config.toxicity_model_name
            probability_mode = "toxicity_obscenity"
        elif args.system == "finetuned":
            model_path = model_path or str(config.output_dir / "fine_tuned_rubert_tiny2" / "best_model")

        device = get_device()
        tokenizer, model = load_sequence_classifier(model_path, device=device)
        batch_size = config.batch_size_gpu if device.type == "cuda" else config.batch_size_cpu

        val_probs, _ = timed_predict(
            args.system,
            validation_df,
            lambda texts: predict_transformer_sliding(
                texts,
                tokenizer,
                model,
                max_length=config.max_length,
                stride=config.stride,
                batch_size=batch_size,
                probability_mode=probability_mode,
            ),
        )
        threshold_info = choose_threshold(
            validation_df["label"].to_numpy(dtype=int),
            val_probs,
            target_recall=config.target_recall,
        )
        probs, elapsed = timed_predict(
            args.system,
            eval_df,
            lambda texts: predict_transformer_sliding(
                texts,
                tokenizer,
                model,
                max_length=config.max_length,
                stride=config.stride,
                batch_size=batch_size,
                probability_mode=probability_mode,
            ),
        )

    metrics = compute_metrics(eval_df, np.asarray(probs), threshold_info.threshold)
    out_dir = config.output_dir / args.system
    out_dir.mkdir(parents=True, exist_ok=True)
    errors = save_error_examples(eval_df, np.asarray(probs), threshold_info.threshold, out_dir, args.split)
    result = {
        "system": args.system,
        "split": args.split,
        "threshold_selection_on_validation": threshold_info.__dict__,
        "metrics": metrics,
        "inference_seconds": elapsed,
        "error_files": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
