"""Create review-only FAQ drafts from official chunk titles; never invent answers."""
from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha1
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.retrieval.canonical import read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Create PENDING_HUMAN_REVIEW FAQ skeletons from official chunks.")
    parser.add_argument("--input", type=Path, default=Path("data/processed/index/all_chunks.jsonl"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=10, help="Small review batch; answers are intentionally empty.")
    args = parser.parse_args()
    drafts = []
    for chunk in read_jsonl(args.input):
        if chunk.get("authority") != "official" or not str(chunk.get("title") or "").strip():
            continue
        title = str(chunk["title"]).strip()
        drafts.append({
            "id": "draft-" + sha1(str(chunk["chunk_id"]).encode()).hexdigest()[:12], "intent": "", "title": title,
            "question_variants": [title], "answer": "", "role": None, "source_chunk_ids": [chunk["chunk_id"]],
            "source_urls": [item for item in [chunk.get("source_url"), (chunk.get("metadata") or {}).get("source_url")] if item],
            "verified": False, "review_status": "PENDING_HUMAN_REVIEW", "reviewed_by": None,
            "reviewed_at": None, "updated_at": None,
        })
        if len(drafts) >= args.limit:
            break
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in drafts), encoding="utf-8")
    print(json.dumps({"created_drafts": len(drafts), "verified": False, "review_status": "PENDING_HUMAN_REVIEW"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
