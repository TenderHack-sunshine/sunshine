from __future__ import annotations

"""Small terminal workflow for explicit human labelling of DEV abstention cases."""

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "data/eval/abstention_calibration_dev.jsonl"
LABELS = {"ANSWERABLE", "INSUFFICIENT_KNOWLEDGE", "AMBIGUOUS_QUERY"}
GAPS = {"NO_RELEVANT_DOCUMENTS", "PARTIAL_KNOWLEDGE"}


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def save(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def show(row: dict) -> None:
    print(json.dumps({key: row.get(key) for key in ("id", "category", "query", "proposed_label", "gap_type", "supporting_evidence", "label_rationale")}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Explicitly record one human DEV review; never auto-approves labels.")
    parser.add_argument("--input", type=Path, default=DEFAULT)
    parser.add_argument("--list", action="store_true", help="Show pending case IDs and exit.")
    parser.add_argument("--case", help="Case ID to review.")
    parser.add_argument("--label", choices=sorted(LABELS), help="Human label; required when updating.")
    parser.add_argument("--gap-type", choices=sorted(GAPS), help="Required only for INSUFFICIENT_KNOWLEDGE.")
    parser.add_argument("--note", help="Required reviewer note explaining the decision.")
    parser.add_argument("--reviewer", help="Human reviewer name/initials; required when updating.")
    args = parser.parse_args()
    rows = load(args.input)
    if args.list:
        for row in rows:
            if row.get("review_status") == "PENDING_HUMAN_REVIEW":
                print(f"{row['id']}\t{row['proposed_label']}\t{row['query']}")
        return
    if not args.case:
        parser.error("--case is required unless --list is used")
    row = next((item for item in rows if item["id"] == args.case), None)
    if row is None:
        parser.error(f"unknown case: {args.case}")
    if not args.label:
        show(row)
        parser.error("Review shown; re-run with --label, --reviewer, and --note to record an explicit human decision")
    if not args.reviewer or not args.note:
        parser.error("--reviewer and --note are required; labels are never auto-approved")
    if args.label == "INSUFFICIENT_KNOWLEDGE" and not args.gap_type:
        parser.error("--gap-type is required for INSUFFICIENT_KNOWLEDGE")
    if args.label != "INSUFFICIENT_KNOWLEDGE" and args.gap_type:
        parser.error("--gap-type is only valid for INSUFFICIENT_KNOWLEDGE")
    row.update({"human_label": args.label, "human_gap_type": args.gap_type, "human_verified": True,
                "review_note": args.note, "reviewer": args.reviewer, "review_status": "HUMAN_REVIEWED"})
    save(args.input, rows)
    print(f"Recorded HUMAN_REVIEWED decision for {row['id']}")


if __name__ == "__main__":
    main()
