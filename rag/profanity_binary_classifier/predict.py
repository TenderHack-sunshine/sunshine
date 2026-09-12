from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from profanity_ml.config import load_config
from profanity_ml.transformer_inference import (
    get_device,
    load_sequence_classifier,
    predict_transformer_sliding,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--config", default="configs/default.json")
    parser.add_argument("--model-dir", default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    model_dir = Path(args.model_dir) if args.model_dir else config.output_dir / "fine_tuned_rubert_tiny2" / "best_model"
    threshold_path = model_dir.parent / "threshold.json"
    if not model_dir.exists():
        raise FileNotFoundError(
            f"Fine-tuned model not found: {model_dir}. Run `python train.py` first."
        )
    if not threshold_path.exists():
        raise FileNotFoundError(
            f"Threshold file not found: {threshold_path}. Run `python train.py` first."
        )

    threshold = json.loads(threshold_path.read_text(encoding="utf-8"))["threshold"]
    device = get_device()
    batch_size = config.batch_size_gpu if device.type == "cuda" else config.batch_size_cpu
    tokenizer, model = load_sequence_classifier(str(model_dir), device=device)
    probability = float(
        predict_transformer_sliding(
            [args.text],
            tokenizer,
            model,
            max_length=config.max_length,
            stride=config.stride,
            batch_size=batch_size,
            probability_mode="binary",
        )[0]
    )
    result = {
        "text": args.text,
        "label": int(probability >= threshold),
        "probability": round(probability, 6),
        "threshold": round(float(threshold), 6),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
