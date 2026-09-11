from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.retrieval.canonical import prepare_canonical_chunks, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge validated KB and local chunks into the canonical indexing corpus.")
    parser.add_argument("--kb-input", type=Path, default=Path("data/processed/zakupki_kb_chunks.jsonl"))
    parser.add_argument("--local-input", type=Path, default=Path("data/processed/files/chunks.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/index/all_chunks.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("data/processed/index/report.json"))
    args = parser.parse_args()
    chunks, report = prepare_canonical_chunks(args.kb_input, args.local_input)
    write_jsonl(args.output, chunks)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
