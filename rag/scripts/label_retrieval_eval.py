from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.application.factory import build_rag_service
from src.core.config import Settings
from src.evaluation.dataset import apply_label, load_jsonl, save_jsonl_atomic


def preview(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def show_case(row: dict, candidates: list[dict]) -> None:
    print(f"\nQuery: {row['query']}")
    print(f"Expected route: {row.get('expected_route', row.get('route', '—'))}")
    print(f"Existing chunk labels: {row.get('relevant_chunk_ids', [])}")
    print(f"Existing document labels: {row.get('relevant_document_ids', [])}")
    print("Top retrieval candidates:")
    for index, item in enumerate(candidates, 1):
        print(f"\n[{index}] source={item.get('source_type')} authority={item.get('authority')} method={item.get('retrieval_method')}")
        print(f"document_id: {item.get('document_id')}\nchunk_id: {item.get('chunk_id')}")
        print(f"title: {item.get('title')}\nsection: {item.get('section')}\nscore: {item.get('reranker_score', item.get('rrf_score', item.get('raw_score')))}")
        print("text preview: " + preview(item.get("text", "")))


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactively add human relevance labels to a retrieval JSONL dataset.")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()
    rows = load_jsonl(args.dataset)
    service = build_rag_service(Settings())
    for index, row in enumerate(rows):
        route = row.get("expected_route", row.get("route"))
        trace = service.retriever.retrieve_with_trace(row["query"], technical=route == "L3", top_k=args.top_k)
        candidates = trace["results"]
        show_case(row, candidates)
        command = input("Label: 1 3=both; c 1=chunk; d 1=document; r 1 3=replace; note text; s=skip; n=none; q=save+quit: ").strip()
        if command == "q":
            save_jsonl_atomic(args.dataset, rows)
            print("Saved backup and labels.")
            return
        try:
            rows[index], outcome = apply_label(row, candidates, command)
            if outcome != "skipped":
                save_jsonl_atomic(args.dataset, rows)
                print(f"{outcome}; saved with backup {args.dataset.name}.bak")
        except ValueError as error:
            print(f"Invalid command: {error}")
    save_jsonl_atomic(args.dataset, rows)
    print("Finished; saved backup and labels.")


if __name__ == "__main__":
    main()
