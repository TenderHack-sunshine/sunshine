from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.application.factory import build_rag_service
from src.core.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="End-to-end Tender Hack support RAG.")
    parser.add_argument("query")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--ticket-index", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    service = build_rag_service(Settings(), canonical_path=args.input, ticket_index_path=args.ticket_index)
    result = service.ask(args.query)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"original_query: {result['original_query']}")
    print(f"normalized_query: {result['normalized_query']}")
    print(f"route: {result['route']}")
    print(f"dense_available: {str(result['diagnostics']['dense_available']).lower()}")
    print(f"fallback_used: {str(result['diagnostics']['fallback_used']).lower()}")
    print(f"decision: {result['status']}")
    print("sources:")
    for source in result["sources"]:
        print(f"  - {source['source_type']} / {source['authority']} / {source['retrieval_method']} / {source['chunk_id']}")
    print(f"answer: {result['answer']}")
    print("timings: " + json.dumps(result["diagnostics"]["timings_ms"], ensure_ascii=False))


if __name__ == "__main__":
    main()
