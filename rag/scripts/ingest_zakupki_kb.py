from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import Settings
from src.ingestion.sources.zakupki_knowledgebase import (
    KnowledgeBaseAPIError,
    ZakupkiKnowledgeBaseClient,
    ingest_knowledgebase_payload,
    load_payload,
)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest structured Moscow Supplier Portal Knowledge Base articles")
    parser.add_argument("--section-type", action="append", dest="section_types", help="API sectionType; may be passed multiple times")
    parser.add_argument("--from-file", type=Path, help="Saved API JSON; performs no network request")
    parser.add_argument("--save-raw", action="store_true", help="Save fetched response under data/raw/zakupki_kb/")
    parser.add_argument("--output", type=Path, default=None, help="Directory for documents/chunks/report JSONL/JSON")
    args = parser.parse_args()
    settings = Settings()
    section_types = args.section_types or list(settings.zakupki_kb_section_types)
    try:
        if args.from_file:
            payload = load_payload(args.from_file)
        else:
            client = ZakupkiKnowledgeBaseClient(settings.zakupki_kb_api_url, settings.zakupki_kb_timeout_seconds, settings.zakupki_kb_max_retries)
            payload = [category for section_type in section_types for category in client.fetch_articles(section_type)]
            if args.save_raw:
                raw_path = settings.data_dir / "raw" / "zakupki_kb" / f"{'_'.join(section_types)}.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"Saved raw API response to {raw_path}")
        documents, chunks, report = ingest_knowledgebase_payload(
            payload, section_type=section_types[0] if len(section_types) == 1 else None,
            base_url=settings.zakupki_kb_base_url, max_chunk_tokens=settings.zakupki_kb_max_chunk_tokens,
        )
    except KnowledgeBaseAPIError as error:
        parser.error(str(error))
    output = args.output or settings.processed_dir
    _write_jsonl(output / "zakupki_kb_documents.jsonl", documents)
    _write_jsonl(output / "zakupki_kb_chunks.jsonl", chunks)
    (output / "zakupki_kb_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
