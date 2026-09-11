from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.main import answer_question
from src.retrieval.mvp import load_two_path_retriever


def _preview(text: str, limit: int = 240) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[:limit - 1] + "…"


def main() -> None:
    parser = argparse.ArgumentParser(description="Intel-friendly two-path Tender Hack retrieval MVP.")
    parser.add_argument("query")
    parser.add_argument("--input", type=Path, default=Path("data/processed/index/all_chunks.jsonl"))
    parser.add_argument("--ticket-index", type=Path, default=Path("data/indexes/support_tickets_bm25.pkl"))
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    retriever = load_two_path_retriever(args.input, args.ticket_index)
    response = answer_question(args.query, retriever)
    print(f"normalized={response['normalized_query']}")
    print(f"route={response['route']}")
    if response["moderation"]["contains_profanity"]:
        print(response["answer"])
        return
    for rank, item in enumerate(response["evidence"][:args.top_k], start=1):
        print(f"#{rank} score={item['score']:.4f} method={item['retrieval_method']} source={item['source_type']} authority={item['authority']}")
        print(f"location={item.get('title') or item.get('source_path')} page={item.get('page_start')}")
        print(f"text={_preview(item['text'])}")
        print(f"chunk_id={item['chunk_id']}\n")
    print("answer_preview=" + _preview(response["answer"]))


if __name__ == "__main__":
    main()
