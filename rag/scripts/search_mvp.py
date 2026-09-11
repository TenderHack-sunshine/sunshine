from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import Settings
from src.main import answer_question
from src.retrieval.embeddings.isolated_qwen3 import IsolatedQwen3QueryEmbedding
from src.retrieval.mvp import load_two_path_retriever
from src.retrieval.official_dense import OfficialDenseRetriever
from src.retrieval.vector_store import HttpQdrantStore


def _preview(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[:limit - 1] + "…"


def _load_active_dense(settings: Settings, *, disabled: bool):
    """Avoid loading Qwen until an official-only collection is known to exist."""
    if disabled:
        return None, "disabled by --disable-dense"
    try:
        store = HttpQdrantStore(settings.qdrant_host, settings.qdrant_port, settings.qdrant_official_collection)
        if not store.collection_exists():
            return None, f"collection {store.collection!r} does not exist"
        return OfficialDenseRetriever(
            IsolatedQwen3QueryEmbedding(settings.embedding_model_path, settings.dense_query_timeout_seconds),
            store,
            query_timeout_seconds=settings.dense_query_timeout_seconds,
        ), None
    except Exception as error:
        return None, f"Qdrant unavailable: {error}"


def _print_candidates(title: str, items: list[dict], score_label: str) -> None:
    print(f"\n{title}:")
    if not items:
        print("  (none)")
        return
    for item in items:
        print(
            f"  #{item.get('rank', '?')} {score_label}={item.get('raw_score', 0.0):.4f} "
            f"method={item.get('retrieval_method')} source={item.get('source_type')} "
            f"authority={item.get('authority')} chunk={item.get('chunk_id')}"
        )


def main() -> None:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Active Tender Hack two-path retrieval MVP.")
    parser.add_argument("query")
    parser.add_argument("--input", type=Path, default=settings.processed_dir / "index" / "all_chunks.jsonl")
    parser.add_argument("--ticket-index", type=Path, default=settings.data_dir / "indexes" / "support_tickets_bm25.pkl")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--disable-dense", action="store_true", help="Exercise the explicit official BM25 fallback.")
    args = parser.parse_args()

    official_dense, initialization_error = _load_active_dense(settings, disabled=args.disable_dense)
    retriever = load_two_path_retriever(args.input, args.ticket_index, official_dense=official_dense, final_candidates=args.top_k)
    response = answer_question(args.query, retriever)
    trace = response["retrieval"]
    print(f"normalized_query={response['normalized_query']}")
    print(f"route={response['route']}")
    print(f"dense_available={str(trace.get('dense_available', False)).lower()} fallback_used={str(trace.get('fallback_used', False)).lower()}")
    if initialization_error:
        print(f"dense_initialization={initialization_error}")
    if trace.get("dense_error"):
        print(f"dense_error={trace['dense_error']}")
    if response["moderation"]["contains_profanity"]:
        print(response["answer"])
        return

    _print_candidates("DENSE OFFICIAL", trace.get("official_dense", []), "cosine")
    _print_candidates("OFFICIAL FALLBACK BM25", trace.get("official_fallback", []), "bm25")
    _print_candidates("BM25 TICKETS", trace.get("ticket_bm25", []), "bm25")
    print("\nFUSED:")
    for rank, item in enumerate(trace.get("fused", [])[:args.top_k], start=1):
        print(
            f"  #{rank} rrf_score={item.get('rrf_score', 0.0):.6f} "
            f"method={item.get('retrieval_method')} source={item.get('source_type')} "
            f"authority={item.get('authority')} chunk={item.get('chunk_id')}"
        )
    print("\nFINAL TOP-K:")
    for rank, item in enumerate(response["evidence"][:args.top_k], start=1):
        print(
            f"  #{rank} rrf_score={item.get('rrf_score', item.get('score', 0.0)):.6f} "
            f"method={item['retrieval_method']} source={item['source_type']} authority={item['authority']}"
        )
        print(f"    location={item.get('title') or item.get('source_path')} page={item.get('page_start')}")
        print(f"    text={_preview(item['text'])}")
    timing = trace.get("timing", {})
    print("\nTIMING (ms): " + " ".join(
        f"{name}={timing.get(name, 0.0):.2f}" for name in (
            "preprocessing_ms", "query_embedding_ms", "dense_search_ms", "bm25_ms", "fusion_ms", "total_retrieval_ms",
        )
    ))
    print("answer_preview=" + _preview(response["answer"]))


if __name__ == "__main__":
    main()
