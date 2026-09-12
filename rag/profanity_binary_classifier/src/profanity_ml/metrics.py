from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


def is_masked_row(row: pd.Series) -> bool:
    text = " ".join(
        str(row.get(col, "")).casefold()
        for col in ("example_type", "transformation", "notes")
    )
    markers = (
        "mask",
        "masked",
        "obfuscat",
        "star",
        "symbol",
        "spacing",
        "latin",
        "digit",
        "typo",
        "repeat",
        "leet",
        "separated",
        "зв",
        "маск",
        "лат",
        "циф",
        "проб",
        "точ",
    )
    return any(marker in text for marker in markers)


def compute_metrics(
    df: pd.DataFrame,
    probabilities: np.ndarray,
    threshold: float,
) -> dict[str, object]:
    y_true = df["label"].to_numpy(dtype=int)
    y_pred = (probabilities >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()

    positive_count = int((y_true == 1).sum())
    clean_count = int((y_true == 0).sum())
    fpr = fp / max(fp + tn, 1)
    fnr = fn / max(fn + tp, 1)

    result: dict[str, object] = {
        "precision_class_1": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall_class_1": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1_class_1": float(f1_score(y_true, y_pred, zero_division=0)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "pr_auc": float(average_precision_score(y_true, probabilities))
        if positive_count
        else None,
        "roc_auc": float(roc_auc_score(y_true, probabilities))
        if positive_count and clean_count
        else None,
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "false_positive_rate": float(fpr),
        "false_negative_rate": float(fnr),
        "false_positives_per_1000_clean": float(fpr * 1000.0),
    }

    result["recall_by_example_type"] = _recall_by_group(
        df, y_pred, "example_type"
    )
    result["recall_by_transformation"] = _recall_by_group(
        df, y_pred, "transformation"
    )
    masked = df.apply(is_masked_row, axis=1)
    result["masked_positive_count"] = int(((df["label"] == 1) & masked).sum())
    result["recall_masked_examples"] = _safe_recall(
        df.loc[masked, "label"].to_numpy(dtype=int),
        y_pred[masked.to_numpy()],
    )
    return result


def _recall_by_group(df: pd.DataFrame, y_pred: np.ndarray, column: str) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for value, part in df.groupby(column, dropna=False):
        idx = part.index.to_numpy()
        y_true = part["label"].to_numpy(dtype=int)
        out[str(value)] = _safe_recall(y_true, y_pred[idx])
    return out


def _safe_recall(y_true: np.ndarray, y_pred: np.ndarray) -> float | None:
    positives = y_true == 1
    if positives.sum() == 0:
        return None
    return float(((y_pred == 1) & positives).sum() / positives.sum())


def timed_predict(
    name: str,
    df: pd.DataFrame,
    predictor: Callable[[list[str]], list[float] | np.ndarray],
) -> tuple[np.ndarray, float]:
    start = perf_counter()
    probabilities = np.asarray(predictor(df["text"].tolist()), dtype=float)
    elapsed = perf_counter() - start
    if probabilities.shape[0] != len(df):
        raise ValueError(f"{name} returned {probabilities.shape[0]} predictions for {len(df)} rows")
    return probabilities, elapsed


def save_error_examples(
    df: pd.DataFrame,
    probabilities: np.ndarray,
    threshold: float,
    output_dir: str | Path,
    prefix: str,
    n: int = 20,
) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    work = df.copy()
    work["probability"] = probabilities
    work["prediction"] = (probabilities >= threshold).astype(int)
    fp = work[(work["label"] == 0) & (work["prediction"] == 1)].sort_values(
        "probability", ascending=False
    )
    fn = work[(work["label"] == 1) & (work["prediction"] == 0)].sort_values(
        "probability", ascending=True
    )
    fp_path = output / f"{prefix}_false_positives_top{n}.csv"
    fn_path = output / f"{prefix}_false_negatives_top{n}.csv"
    fp.head(n).to_csv(fp_path, index=False, encoding="utf-8-sig")
    fn.head(n).to_csv(fn_path, index=False, encoding="utf-8-sig")
    return {"false_positives": str(fp_path), "false_negatives": str(fn_path)}


def flatten_metrics_for_table(system: str, split: str, metrics: dict[str, object], inference_seconds: float) -> dict[str, object]:
    return {
        "system": system,
        "split": split,
        "precision": metrics["precision_class_1"],
        "recall": metrics["recall_class_1"],
        "f1": metrics["f1_class_1"],
        "pr_auc": metrics["pr_auc"],
        "fp_per_1000_clean": metrics["false_positives_per_1000_clean"],
        "inference_seconds": inference_seconds,
    }
