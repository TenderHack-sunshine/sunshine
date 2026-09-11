from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import Settings
from src.retrieval.dense import DenseRetriever
from src.retrieval.embeddings.qwen3 import Qwen3Embedding
from src.retrieval.vector_store import QdrantStore


def _keyword_match(results: list[dict], keywords: list[str]) -> bool:
    text = " ".join(result.get("text", "").casefold() for result in results)
    return any(keyword.casefold() in text for keyword in keywords)


def main() -> None:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Lightweight Recall@5-style smoke evaluation for dense retrieval.")
    parser.add_argument("--eval", type=Path, default=Path("data/eval/retrieval_smoke.json"))
    parser.add_argument("--collection", default=settings.qdrant_collection)
    args = parser.parse_args()
    cases = json.loads(args.eval.read_text(encoding="utf-8"))
    retriever = DenseRetriever(Qwen3Embedding(settings.embedding_model_path), QdrantStore(collection=args.collection))
    passed = 0
    for case in cases:
        results = retriever.retrieve(case["query"], top_k=5)
        source_types = [result.get("source_type") for result in results]
        top1 = bool(results) and results[0].get("source_type") == case["expected_source_type"] and _keyword_match(results[:1], case["expected_keywords"])
        top5 = case["expected_source_type"] in source_types and _keyword_match(results, case["expected_keywords"])
        passed += top5
        print(json.dumps({"query": case["query"], "top1_relevant": top1, "top5_relevant": top5, "source_types_top5": source_types}, ensure_ascii=False))
    print(json.dumps({"queries": len(cases), "recall_at_5_like": passed / len(cases) if cases else 0.0}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
