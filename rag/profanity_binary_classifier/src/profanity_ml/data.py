from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {
    "id",
    "text",
    "label",
    "split",
    "group_id",
    "example_type",
    "transformation",
    "source",
    "review_status",
    "notes",
    "language",
}
ALLOWED_SPLITS = {"train", "validation", "test"}


@dataclass(frozen=True)
class DataValidationReport:
    row_count_by_split: dict[str, int]
    class_count_by_split: dict[str, dict[int, int]]
    class_share_by_split: dict[str, dict[int, float]]


def load_dataset(path: str | Path) -> pd.DataFrame:
    df = pd.read_excel(path)
    missing = REQUIRED_COLUMNS.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    df = df.copy()
    df["text"] = df["text"].astype(str)
    df["split"] = df["split"].astype(str)
    df["label"] = df["label"].astype(int)
    return df


def validate_dataset(df: pd.DataFrame) -> DataValidationReport:
    errors: list[str] = []

    empty_text = df["text"].isna() | (df["text"].astype(str).str.strip() == "")
    if empty_text.any():
        errors.append(f"Empty text rows: {int(empty_text.sum())}")

    labels = set(df["label"].dropna().astype(int).unique().tolist())
    if labels != {0, 1}:
        errors.append(f"Labels must be exactly {{0, 1}}, got {sorted(labels)}")

    splits = set(df["split"].dropna().astype(str).unique().tolist())
    unknown_splits = splits.difference(ALLOWED_SPLITS)
    missing_splits = ALLOWED_SPLITS.difference(splits)
    if unknown_splits or missing_splits:
        errors.append(
            f"Splits must be {sorted(ALLOWED_SPLITS)}, got {sorted(splits)}"
        )

    duplicate_text_count = int(df["text"].duplicated(keep=False).sum())
    if duplicate_text_count:
        errors.append(f"Duplicate text rows: {duplicate_text_count}")

    group_split_counts = df.groupby("group_id")["split"].nunique(dropna=False)
    leaking_groups = group_split_counts[group_split_counts > 1]
    if not leaking_groups.empty:
        errors.append(
            "group_id crossing splits: "
            f"{len(leaking_groups)} groups, examples={leaking_groups.index[:10].tolist()}"
        )

    text_split_counts = df.groupby("text")["split"].nunique(dropna=False)
    leaking_texts = text_split_counts[text_split_counts > 1]
    if not leaking_texts.empty:
        errors.append(
            "Duplicate text between splits: "
            f"{len(leaking_texts)} texts, examples={leaking_texts.index[:5].tolist()}"
        )

    if errors:
        raise ValueError("Dataset validation failed:\n- " + "\n- ".join(errors))

    counts = df.groupby("split").size().reindex(sorted(ALLOWED_SPLITS), fill_value=0)
    class_counts_df = (
        df.groupby(["split", "label"]).size().unstack(fill_value=0).reindex(
            sorted(ALLOWED_SPLITS), fill_value=0
        )
    )
    for label in (0, 1):
        if label not in class_counts_df.columns:
            class_counts_df[label] = 0
    class_counts_df = class_counts_df[[0, 1]]
    class_shares_df = class_counts_df.div(class_counts_df.sum(axis=1), axis=0)

    return DataValidationReport(
        row_count_by_split={str(k): int(v) for k, v in counts.items()},
        class_count_by_split={
            str(split): {int(label): int(value) for label, value in row.items()}
            for split, row in class_counts_df.to_dict(orient="index").items()
        },
        class_share_by_split={
            str(split): {int(label): float(value) for label, value in row.items()}
            for split, row in class_shares_df.fillna(0).to_dict(orient="index").items()
        },
    )


def split_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = df[df["split"] == "train"].reset_index(drop=True)
    validation = df[df["split"] == "validation"].reset_index(drop=True)
    test = df[df["split"] == "test"].reset_index(drop=True)
    return train, validation, test
