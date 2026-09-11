from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.chunker import chunk_document
from src.ingestion.chunker import approximate_token_count
from src.ingestion.parsers.base import SUPPORTED_SUFFIXES, parse_file, stable_local_document_id
from src.ingestion.parsers.xlsx import parse_xlsx


def _write_jsonl(path: Path, records: list[dict], profile: dict[str, float | int] | None = None) -> None:
    started = perf_counter()
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    if profile is not None:
        profile["jsonl_writing_seconds"] = float(profile.get("jsonl_writing_seconds", 0.0)) + perf_counter() - started


def _write_record(file: TextIO | None, record: dict, profile: dict[str, float | int]) -> None:
    if file is None:
        return
    started = perf_counter()
    file.write(json.dumps(record, ensure_ascii=False) + "\n")
    profile["jsonl_writing_seconds"] = float(profile.get("jsonl_writing_seconds", 0.0)) + perf_counter() - started


def _timed_token_counter(profile: dict[str, float | int]):
    """A per-run cache prevents repeated regex tokenization of identical text."""
    cache: dict[str, int] = {}

    def count(text: str) -> int:
        profile["token_count_calls"] = int(profile.get("token_count_calls", 0)) + 1
        cached = cache.get(text)
        if cached is not None:
            profile["token_count_cache_hits"] = int(profile.get("token_count_cache_hits", 0)) + 1
            return cached
        started = perf_counter()
        value = approximate_token_count(text)
        profile["token_count_seconds"] = float(profile.get("token_count_seconds", 0.0)) + perf_counter() - started
        cache[text] = value
        return value

    return count


def _display(value: object) -> str:
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def _skip(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return (
        "zakupki_kb" in relative.parts
        or any(part.startswith(".") for part in relative.parts)
        or path.name.startswith("~$")
        or path.name in {".DS_Store", "Thumbs.db"}
    )


def _source_semantics(relative_path: str, suffix: str, document: dict) -> tuple[str, str]:
    if suffix == ".pdf":
        return "official_manual", "official"
    if relative_path.casefold() == "tickets/выгрузка стп за 2026.xlsx":
        return "support_ticket", "case_history"
    if relative_path.casefold() == "tickets/темы_подтемы_обращений.xlsx":
        return "support_taxonomy", "taxonomy"
    return document.get("source_type", "local_file"), document.get("authority", "unknown")


def _ticket_context(document: dict) -> str:
    return "\n".join(part for part in (
        f"Тема: {document['topic']}" if document.get("topic") else "",
        f"Подтема: {document['subtopic']}" if document.get("subtopic") else "",
    ) if part)


def _chunk_ticket(document: dict, chunk_size: int, chunk_overlap: int,
                  token_counter=approximate_token_count, profile: dict[str, float | int] | None = None) -> list[dict]:
    """Split long tickets by prose while repeating enough context for every continuation."""
    context = _ticket_context(document)
    body = "\n".join(part for part in (
        f"Проблема: {document['description']}" if document.get("description") else "",
        f"Решение: {document['solution']}" if document.get("solution") else "",
    ) if part) or document["text"]
    text = f"{context}\n{body}".strip()
    token_count = token_counter(text)
    if token_count <= chunk_size:
        # The overwhelmingly common ticket is already a complete retrieval unit.
        return [{
            "text": text, "source": document.get("source"), "page_start": None, "page_end": None, "page": None,
            "section": document.get("section"), "chunk_index": 0, "token_count": token_count,
            "authority": document.get("authority", "case_history"), "document_type": "support_ticket",
            "chunking_strategy": "recursive", "unit_count": 1, "semantic_break_score": None,
        }]
    started = perf_counter()
    body_limit = max(1, chunk_size - token_counter(context))
    parts = chunk_document(
        {**document, "text": body, "source": "local_file"}, chunk_size=body_limit,
        # Context is repeated below; body overlap could otherwise violate the hard maximum.
        overlap_paragraphs=0, min_chunk_tokens=1, token_counter=token_counter,
    )
    if profile is not None:
        profile["oversized_row_splitting_seconds"] = float(profile.get("oversized_row_splitting_seconds", 0.0)) + perf_counter() - started
    return [{**part, "text": f"{context}\n{part['text']}".strip(), "token_count": token_counter(f"{context}\n{part['text']}".strip())} for part in parts]


def ingest_local_files(input_dir: Path, chunk_size: int = 700, chunk_overlap: int = 1,
                       limit: int | None = None, verbose: bool = False, *, row_limit: int | None = None,
                       progress_every: int = 1000, document_writer: TextIO | None = None,
                       chunk_writer: TextIO | None = None,
                       profile: dict[str, float | int] | None = None) -> tuple[list[dict], list[dict], dict]:
    if not input_dir.is_dir():
        raise ValueError(f"Input directory does not exist: {input_dir}")
    chunk_size = min(chunk_size, 800)
    profile = profile if profile is not None else {}
    token_counter = _timed_token_counter(profile)
    started = perf_counter()
    documents: list[dict] = []
    chunks: list[dict] = []
    formats, failed = Counter(), []
    input_files = unsupported = 0
    warnings: list[str] = ["Skipped data/raw/zakupki_kb; use scripts/ingest_zakupki_kb.py for that dedicated source."] if (input_dir / "zakupki_kb").is_dir() else []
    candidates = [path for path in sorted(input_dir.rglob("*")) if path.is_file() and not _skip(path, input_dir)]
    for path in candidates[:limit]:
        input_files += 1
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            unsupported += 1
            if verbose:
                print(f"Unsupported: {_display(path)}")
            continue
        relative_path = path.relative_to(input_dir).as_posix()
        try:
            if suffix == ".xlsx":
                parsed = parse_xlsx(
                    path, row_limit=row_limit, profile=profile, progress_every=progress_every,
                    progress_callback=(
                        lambda processed, total, _path: print(f"[{processed}/{total}] elapsed={perf_counter() - started:.1f}s")
                        if verbose else None
                    ),
                )
            else:
                parsed = parse_file(path)
        except Exception as error:
            failed.append({"path": relative_path, "error": str(error)})
            if verbose:
                print(f"Failed: {_display(path)} ({_display(error)})")
            continue
        formats[suffix.lstrip(".")] += 1
        if verbose:
            print(f"Parsed: {_display(path)} ({len(parsed)} documents)")
        file_document_id = stable_local_document_id(relative_path)
        file_chunk_index = 0
        for part_index, document in enumerate(parsed):
            text = document.get("text", "").strip()
            if not text:
                warnings.append(f"Empty output skipped: {relative_path}")
                continue
            part = next(
                (value for value in (document.get("page"), document.get("row"), document.get("record")) if value is not None),
                part_index,
            )
            document_id = file_document_id if suffix == ".pdf" else f"{file_document_id}:{part}"
            source_type, authority = _source_semantics(relative_path, suffix, document)
            normalized = {
                **document, "document_id": document_id, "source": "local_file", "source_path": relative_path,
                "file_type": suffix.lstrip("."), "original_source": document.get("source"),
                "source_type": source_type, "authority": authority,
            }
            normalized["metadata"] = {key: normalized.get(key) for key in (
                "sheet", "row", "record", "title", "links", "likely_scanned", "influence", "topic", "subtopic",
                "status", "description", "solution",
            ) if normalized.get(key) is not None}
            documents.append(normalized)
            _write_record(document_writer, normalized, profile)
            minimum_tokens = 1 if normalized.get("document_type") in {"table_row", "json_record", "support_taxonomy"} else 50
            raw_chunks = (_chunk_ticket(normalized, chunk_size, chunk_overlap, token_counter, profile)
                          if normalized.get("document_type") == "support_ticket" else chunk_document(
                              {**normalized, "source": "local_file"}, chunk_size=chunk_size,
                              overlap_paragraphs=chunk_overlap, min_chunk_tokens=minimum_tokens, token_counter=token_counter,
                          ))
            if not raw_chunks:
                warnings.append(f"No meaningful chunks emitted: {relative_path} part {part}")
            for chunk_index, chunk in enumerate(raw_chunks):
                actual_chunk_index = file_chunk_index if suffix == ".pdf" else chunk_index
                if suffix == ".pdf":
                    file_chunk_index += 1
                output_chunk = {
                    **chunk, "chunk_id": f"{document_id}:{actual_chunk_index}", "document_id": document_id,
                    "source": "local_file", "source_path": relative_path, "file_type": suffix.lstrip("."),
                    "source_type": source_type, "authority": authority, "chunk_index": actual_chunk_index,
                    "metadata": normalized["metadata"],
                }
                chunks.append(output_chunk)
                _write_record(chunk_writer, output_chunk, profile)
    report = {
        "input_files": input_files, "parsed_documents": len(documents), "failed_files": len(failed),
        "unsupported_files": unsupported, "chunks": len(chunks), "formats": dict(formats), "failed": failed,
        "warnings": warnings,
        "timing_seconds": {key: value for key, value in profile.items() if key.endswith("_seconds")},
        "performance": {key: value for key, value in profile.items() if not key.endswith("_seconds")},
    }
    return documents, chunks, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse and chunk supported local files; dedicated Knowledge Base JSON is skipped.")
    parser.add_argument("--input", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/files"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--row-limit", type=int, help="Maximum emitted rows per XLSX source; useful for profiling.")
    parser.add_argument("--progress-every", type=int, default=1000, help="Print ticket-row progress at this interval with --verbose.")
    parser.add_argument("--force", action="store_true", help="Overwrite this command's prior JSONL/report files.")
    parser.add_argument("--chunk-size", type=int, default=700)
    parser.add_argument("--chunk-overlap", type=int, default=1, help="Paragraph overlap for forced local-file splits.")
    parser.add_argument("--enable-ocr", action="store_true", help="Reserved; OCR is not bundled in the local MVP.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if args.chunk_size <= 0 or args.chunk_overlap < 0 or args.progress_every <= 0:
        parser.error("--chunk-size and --progress-every must be positive and --chunk-overlap cannot be negative")
    output_files = [args.output / name for name in ("documents.jsonl", "chunks.jsonl", "report.json")]
    if not args.force and any(path.exists() for path in output_files):
        parser.error(f"Output already exists under {args.output}; pass --force to replace this run's files.")
    args.output.mkdir(parents=True, exist_ok=True)
    profile: dict[str, float | int] = {}
    with output_files[0].open("w", encoding="utf-8") as document_file, output_files[1].open("w", encoding="utf-8") as chunk_file:
        documents, chunks, report = ingest_local_files(
            args.input, args.chunk_size, args.chunk_overlap, args.limit, args.verbose,
            row_limit=args.row_limit, progress_every=args.progress_every,
            document_writer=document_file, chunk_writer=chunk_file, profile=profile,
        )
    if args.enable_ocr:
        report["warnings"].append("OCR is not installed; likely scanned PDF pages remain metadata-only.")
    output_files[2].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
