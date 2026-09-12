from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.metrics import f1_score, precision_recall_curve


@dataclass(frozen=True)
class ThresholdSelection:
    threshold: float
    precision: float
    recall: float
    f1: float
    target_recall: float
    target_recall_satisfied: bool
    reason: str


def choose_threshold(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    target_recall: float = 0.95,
) -> ThresholdSelection:
    precision, recall, thresholds = precision_recall_curve(y_true, probabilities)
    candidates = []
    for idx, threshold in enumerate(thresholds):
        candidates.append((float(threshold), float(precision[idx]), float(recall[idx])))

    feasible = [item for item in candidates if item[2] >= target_recall]
    if feasible:
        threshold, prec, rec = max(feasible, key=lambda item: (item[1], item[0]))
        y_pred = (probabilities >= threshold).astype(int)
        return ThresholdSelection(
            threshold=threshold,
            precision=prec,
            recall=rec,
            f1=float(f1_score(y_true, y_pred, zero_division=0)),
            target_recall=target_recall,
            target_recall_satisfied=True,
            reason=f"max precision with recall >= {target_recall}",
        )

    unique_thresholds = np.unique(probabilities)
    if unique_thresholds.size == 0:
        unique_thresholds = np.array([0.5])
    scored = []
    for threshold in unique_thresholds:
        y_pred = (probabilities >= threshold).astype(int)
        scored.append(
            (
                float(threshold),
                float(f1_score(y_true, y_pred, zero_division=0)),
                float(((y_pred == 1) & (y_true == 1)).sum() / max((y_true == 1).sum(), 1)),
            )
        )
    threshold, f1, rec = max(scored, key=lambda item: (item[1], item[2], item[0]))
    y_pred = (probabilities >= threshold).astype(int)
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    prec = tp / max(tp + fp, 1)
    return ThresholdSelection(
        threshold=threshold,
        precision=float(prec),
        recall=rec,
        f1=f1,
        target_recall=target_recall,
        target_recall_satisfied=False,
        reason=f"no threshold reached recall >= {target_recall}; selected max F1",
    )
