from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, Dataset
from tqdm.auto import tqdm
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

from .metrics import compute_metrics
from .threshold import choose_threshold
from .transformer_inference import get_device, predict_transformer_sliding


class TextDataset(Dataset):
    def __init__(self, df: pd.DataFrame, tokenizer, max_length: int):
        self.texts = df["text"].astype(str).tolist()
        self.labels = df["label"].astype(int).tolist()
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.texts)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        encoded = self.tokenizer(
            self.texts[idx],
            max_length=self.max_length,
            truncation=True,
            padding="max_length",
            return_tensors="pt",
        )
        return {
            "input_ids": encoded["input_ids"].squeeze(0),
            "attention_mask": encoded["attention_mask"].squeeze(0),
            "labels": torch.tensor(self.labels[idx], dtype=torch.long),
        }


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def train_fine_tuned_model(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    model_name: str,
    output_dir: str | Path,
    seed: int,
    max_length: int,
    stride: int,
    learning_rate: float,
    batch_size_gpu: int,
    batch_size_cpu: int,
    epochs: int,
    min_epochs: int,
    weight_decay: float,
    early_stopping_patience: int,
    target_recall: float,
) -> dict[str, object]:
    set_seed(seed)
    output = Path(output_dir)
    best_dir = output / "best_model"
    output.mkdir(parents=True, exist_ok=True)
    logs_path = output / "train_log.jsonl"

    device = get_device()
    batch_size = batch_size_gpu if device.type == "cuda" else min(batch_size_cpu, batch_size_gpu)

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=2)
    model.to(device)

    train_loader = DataLoader(
        TextDataset(train_df, tokenizer, max_length),
        batch_size=batch_size,
        shuffle=True,
    )
    validation_loader = DataLoader(
        TextDataset(validation_df, tokenizer, max_length),
        batch_size=batch_size,
        shuffle=False,
    )
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=learning_rate,
        weight_decay=weight_decay,
    )
    total_steps = max(len(train_loader) * epochs, 1)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(0.1 * total_steps),
        num_training_steps=total_steps,
    )

    best_pr_auc = -1.0
    best_epoch = -1
    patience_left = early_stopping_patience
    history: list[dict[str, object]] = []

    logs_path.write_text("", encoding="utf-8")
    for epoch in range(1, epochs + 1):
        model.train()
        train_losses: list[float] = []
        for batch in tqdm(train_loader, desc=f"train epoch {epoch}"):
            optimizer.zero_grad(set_to_none=True)
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(**batch)
            loss = outputs.loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            train_losses.append(float(loss.detach().cpu().item()))

        model.eval()
        validation_losses: list[float] = []
        with torch.inference_mode():
            for batch in validation_loader:
                batch = {k: v.to(device) for k, v in batch.items()}
                loss = model(**batch).loss
                validation_losses.append(float(loss.detach().cpu().item()))
        val_probs = predict_transformer_sliding(
            validation_df["text"].astype(str).tolist(),
            tokenizer,
            model,
            max_length=max_length,
            stride=stride,
            batch_size=batch_size,
            probability_mode="binary",
        )
        threshold_info = choose_threshold(
            validation_df["label"].to_numpy(dtype=int),
            val_probs,
            target_recall=target_recall,
        )
        val_metrics = compute_metrics(validation_df, val_probs, threshold_info.threshold)
        record = {
            "epoch": epoch,
            "device": str(device),
            "batch_size": batch_size,
            "train_loss": float(np.mean(train_losses)) if train_losses else float("nan"),
            "validation_loss": float(np.mean(validation_losses))
            if validation_losses
            else float("nan"),
            "validation_pr_auc": val_metrics["pr_auc"],
            "validation_precision": val_metrics["precision_class_1"],
            "validation_recall": val_metrics["recall_class_1"],
            "threshold": threshold_info.threshold,
            "threshold_reason": threshold_info.reason,
        }
        history.append(record)
        with logs_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        current_pr_auc = float(val_metrics["pr_auc"])
        if current_pr_auc > best_pr_auc:
            best_pr_auc = current_pr_auc
            best_epoch = epoch
            patience_left = early_stopping_patience
            model.save_pretrained(best_dir)
            tokenizer.save_pretrained(best_dir)
            (output / "best_validation_metrics.json").write_text(
                json.dumps(val_metrics, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (output / "threshold.json").write_text(
                json.dumps(threshold_info.__dict__, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            patience_left -= 1

        if epoch >= min_epochs and patience_left <= 0:
            break

    training_summary = {
        "model_name": model_name,
        "best_model_dir": str(best_dir),
        "seed": seed,
        "device": str(device),
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "weight_decay": weight_decay,
        "max_length": max_length,
        "stride": stride,
        "epochs_requested": epochs,
        "epochs_completed": len(history),
        "best_epoch": best_epoch,
        "best_validation_pr_auc": best_pr_auc,
        "history": history,
    }
    (output / "training_summary.json").write_text(
        json.dumps(training_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return training_summary
