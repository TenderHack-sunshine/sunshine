"""Reproducible inventory of raw materials and their canonical coverage.

It deliberately reports KB completeness as unverifiable when no source export
was retained.  A number of chunks is not evidence that a public web site was
fully ingested.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.retrieval.canonical import read_jsonl


REQUIRED_LOCAL = (
    "manuals/Инструкция по электронному актированию.pdf",
    "manuals/Инструкция по работе с машиночитаемыми доверенностями.pdf",
    "manuals/Инструкция по работе с Порталом для заказчика.pdf",
    "manuals/Инструкция по работе с Порталом для поставщика.pdf",
    "manuals/Инструкция по созданию оферты и СТЕ.pdf",
    "manuals/Инструкция по формированию YML.pdf",
    "tickets/Темы_подтемы_обращений.xlsx",
    "tickets/Выгрузка СТП за 2026.xlsx",
)


def audit(raw_dir: Path, canonical_path: Path) -> dict:
    chunks = list(read_jsonl(canonical_path)) if canonical_path.is_file() else []
    by_path: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks:
        if chunk.get("source_path"):
            by_path[str(chunk["source_path"])].append(chunk)

    materials = []
    for relative in REQUIRED_LOCAL:
        path = raw_dir / relative
        covered = by_path.get(relative, [])
        document_ids = sorted({str(item.get("document_id")) for item in covered})
        materials.append({
            "required_material": relative,
            "raw_present": path.is_file(),
            "canonical_chunks": len(covered),
            "canonical_document_count": len(document_ids),
            "canonical_document_id_sample": document_ids[:5],
            "status": "INCLUDED" if path.is_file() and covered else "MISSING_FROM_CANONICAL" if path.is_file() else "RAW_FILE_MISSING",
        })

    kb_raw = raw_dir / "zakupki_kb"
    kb_chunks = [chunk for chunk in chunks if chunk.get("source_type") == "official_kb"]
    raw_exports = sorted(path.name for path in kb_raw.glob("*.json")) if kb_raw.is_dir() else []
    kb_status = "VERIFIABLE_SOURCE_EXPORT_PRESENT" if raw_exports else "UNVERIFIABLE_NO_SOURCE_EXPORT"
    return {
        "canonical_path": str(canonical_path),
        "canonical_exists": canonical_path.is_file(),
        "canonical_chunk_count": len(chunks),
        "source_type_distribution": dict(sorted(Counter(str(chunk.get("source_type")) for chunk in chunks).items())),
        "authority_distribution": dict(sorted(Counter(str(chunk.get("authority")) for chunk in chunks).items())),
        "materials": materials,
        "zakupki_mos_knowledge_base": {
            "canonical_chunks": len(kb_chunks),
            "canonical_documents": len({chunk.get("document_id") for chunk in kb_chunks}),
            "raw_export_files": raw_exports,
            "completeness_status": kb_status,
            "statement": (
                "Полноту относительно zakupki.mos.ru подтвердить невозможно: исходная выгрузка базы знаний отсутствует."
                if kb_status == "UNVERIFIABLE_NO_SOURCE_EXPORT" else
                "Сравнение полноты возможно только по сохранённой выгрузке и её manifest."
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit required input materials against canonical corpus.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--canonical", type=Path, default=Path("data/processed/index/all_chunks.jsonl"))
    parser.add_argument("--output", type=Path, help="Optional JSON report path; stdout is always emitted.")
    args = parser.parse_args()
    report = audit(args.raw_dir, args.canonical)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
