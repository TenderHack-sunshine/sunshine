from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.retrieval.bm25 import RussianBM25Retriever
from src.retrieval.canonical import read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local sparse BM25 index for historical support tickets.")
    parser.add_argument("--input", type=Path, default=Path("data/processed/index/all_chunks.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/indexes/support_tickets_bm25.pkl"))
    parser.add_argument("--report", type=Path, default=Path("data/indexes/support_tickets_bm25_report.json"))
    args = parser.parse_args()
    tickets = (chunk for chunk in read_jsonl(args.input) if chunk.get("source_type") == "support_ticket")
    retriever = RussianBM25Retriever()
    elapsed = retriever.build(tickets)
    retriever.save(args.output)
    report = {
        "documents": len(retriever.documents), "build_seconds": elapsed,
        "unique_terms": len(retriever.postings), "serialized_size_bytes": args.output.stat().st_size,
        "in_memory_index_size_estimate_bytes": retriever.approximate_size_bytes,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
