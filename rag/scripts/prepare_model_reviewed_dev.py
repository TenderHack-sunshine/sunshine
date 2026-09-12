from __future__ import annotations

"""Materialize MODEL_REVIEWED DEV labels from the supplied review summary.

This is a strict join, not an auto-labeller: it copies reviewer-provided CSV
values verbatim and refuses any ID/query mismatch.
"""

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/eval/abstention_calibration_dev.jsonl"
SUMMARY = ROOT / "data/eval/abstention_calibration_dev_review_summary.csv"
OUT = ROOT / "data/eval/abstention_calibration_dev_reviewed.jsonl"


def main() -> None:
    base = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line]
    with SUMMARY.open(encoding="utf-8", newline="") as handle:
        reviews = {row["id"]: row for row in csv.DictReader(handle)}
    if set(reviews) != {row["id"] for row in base}:
        raise ValueError("review summary IDs do not exactly match DEV IDs")
    output = []
    for row in base:
        review = reviews[row["id"]]
        if review["query"] != row["query"]:
            raise ValueError(f"query mismatch for {row['id']}")
        merged = dict(row)
        merged.update({
            "model_label": review["reviewed_label"],
            "model_gap_type": review["gap_type"] or None,
            "model_review_note": review["review_note"],
            "review_status": "MODEL_REVIEWED",
            "label_source": "MODEL_REVIEWED_FROM_REVIEW_SUMMARY",
        })
        output.append(merged)
    OUT.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in output), encoding="utf-8")
    print(f"Wrote {len(output)} MODEL_REVIEWED DEV records to {OUT}")


if __name__ == "__main__":
    main()
