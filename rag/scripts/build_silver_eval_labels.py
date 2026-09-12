"""Create reproducible, conservative SILVER labels for retrieval evaluation.

This script never modifies the source evaluation set.  The mappings below were
made by reviewing the union of BM25, dense and hybrid top-10 candidates and,
where needed, the matching chunks in ``all_chunks.jsonl``.  They are useful for
repeatability, but are not human gold labels.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluation.dataset import load_jsonl, save_jsonl_atomic


SOURCE = ROOT / "data" / "eval" / "retrieval_eval.jsonl"
OUTPUT = ROOT / "data" / "eval" / "retrieval_eval_silver.jsonl"
CHUNKS = ROOT / "data" / "processed" / "index" / "all_chunks.jsonl"
INSPECTION = ROOT / "data" / "processed" / "eval" / "silver_inspection.json"
REPORT = ROOT / "data" / "processed" / "eval" / "silver_labeling_report.md"


# Indexes match the source JSONL rows, rather than query strings: the input
# deliberately contains the same query twice and both rows must remain present.
LABELS: dict[int, dict[str, Any]] = {
    0: {"status": "LABELED", "reason": "Official KB directly gives both profile paths and XML upload steps.", "docs": ["zakupki_kb:559615"], "chunks": ["zakupki_kb:559615:0"]},
    1: {"status": "AMBIGUOUS", "reason": "Offer signing failure has no error text or status; several distinct remedies are plausible.", "decision": "CLARIFY"},
    2: {"status": "AMBIGUOUS", "reason": "The failed feature and symptoms are not specified.", "decision": "CLARIFY"},
    3: {"status": "LABELED", "reason": "Official manual directly identifies the XML upload field and Add button.", "docs": ["local:023f5bb90dc4ac0eca02852a312e9364a3ff7f8f", "zakupki_kb:559615"], "chunks": ["local:023f5bb90dc4ac0eca02852a312e9364a3ff7f8f:1", "zakupki_kb:559615:0"]},
    4: {"status": "LABELED", "reason": "Official KB directly explains attaching an MChD to a user profile.", "docs": ["zakupki_kb:559615"], "chunks": ["zakupki_kb:559615:0"]},
    5: {"status": "LABELED", "reason": "Typo-normalized query is answered directly by the official MChD upload article.", "docs": ["zakupki_kb:559615"], "chunks": ["zakupki_kb:559615:0"]},
    6: {"status": "LABELED", "reason": "Official KB gives the requested profile location and XML upload procedure.", "docs": ["zakupki_kb:559615", "local:023f5bb90dc4ac0eca02852a312e9364a3ff7f8f"], "chunks": ["zakupki_kb:559615:0", "local:023f5bb90dc4ac0eca02852a312e9364a3ff7f8f:1"]},
    7: {"status": "LABELED", "reason": "Official registration overview directly answers the general supplier-registration question.", "docs": ["zakupki_kb:563652"], "chunks": ["zakupki_kb:563652:0"]},
    8: {"status": "LABELED", "reason": "Official KB supplies the access-recovery path for an unavailable personal account.", "docs": ["zakupki_kb:559705"], "chunks": ["zakupki_kb:559705:0"]},
    9: {"status": "REVIEW_NEEDED", "reason": "Retrieved material covers upload generally or different historical errors, not why this MChD is absent after upload."},
    10: {"status": "AMBIGUOUS", "reason": "No button, page, or resulting error is named.", "decision": "CLARIFY"},
    11: {"status": "AMBIGUOUS", "reason": "It is unclear whether the user means an offer, contract, signature, or another action.", "decision": "CLARIFY"},
    12: {"status": "AMBIGUOUS", "reason": "Offer signing failure has no error text or status; several distinct remedies are plausible.", "decision": "CLARIFY"},
    13: {"status": "REVIEW_NEEDED", "reason": "The error while adding MChD is unspecified; the candidate ticket describes a different concrete validation error."},
    14: {"status": "LABELED", "reason": "Official KB specifically addresses an active quotation-session page that does not display.", "docs": ["zakupki_kb:559982"], "chunks": ["zakupki_kb:559982:0"]},
    15: {"status": "LABELED", "reason": "Official KB lists supported ways to create offers and STE items.", "docs": ["zakupki_kb:225884"], "chunks": ["zakupki_kb:225884:0"]},
    16: {"status": "REVIEW_NEEDED", "reason": "Changing profile data depends on which user or company attribute must be changed; no single candidate covers that generic request."},
    17: {"status": "NO_RELEVANT_EVIDENCE", "reason": "The corpus has the taxonomy data but no authoritative instruction for where a user views support topics."},
    18: {"status": "LABELED", "reason": "Official KB directly states who may act as a supplier on the portal.", "docs": ["zakupki_kb:576047"], "chunks": ["zakupki_kb:576047:0"]},
    19: {"status": "AMBIGUOUS", "reason": "Rules for contract work span separate signing, execution and EDO processes.", "decision": "CLARIFY"},
    20: {"status": "LABELED", "reason": "Official KB directly describes the available methods for creating and publishing offers.", "docs": ["zakupki_kb:225884"], "chunks": ["zakupki_kb:225884:0"]},
    21: {"status": "LABELED", "reason": "The electronic-execution manual materially covers the act/UPD workflow; no isolated chunk is sufficient on its own.", "docs": ["local:76a3d7498623c29bc3d70e982e64cdee7f13dcb9"]},
    22: {"status": "REVIEW_NEEDED", "reason": "The XML upload procedure is present, but the actual upload error is not specified and historical cases are error-specific."},
    23: {"status": "REVIEW_NEEDED", "reason": "No retrieved official source explains a generic HTTP 500 on an offer page."},
    24: {"status": "REVIEW_NEEDED", "reason": "Candidates offer browser and page advice for narrower scenarios, not a verified generic portal freeze remedy."},
    25: {"status": "LABELED", "reason": "Official KB explicitly states that deletion is unavailable and gives the archive alternative.", "docs": ["zakupki_kb:225669"], "chunks": ["zakupki_kb:225669:0"]},
    26: {"status": "NO_RELEVANT_EVIDENCE", "reason": "No retrieved source defines UPD for this broad question; it only contains task-specific UPD procedures."},
    27: {"status": "AMBIGUOUS", "reason": "The document type and requested kind of help are not specified.", "decision": "CLARIFY"},
    28: {"status": "LABELED", "reason": "Official KB establishes that an offer may be changed or withdrawn only before acceptance closes.", "docs": ["zakupki_kb:562811"], "chunks": ["zakupki_kb:562811:0"]},
    29: {"status": "NO_RELEVANT_EVIDENCE", "reason": "No specific portal function is named, so retrieved general manuals cannot answer it."},
    30: {"status": "NO_RELEVANT_EVIDENCE", "reason": "The corpus contains no verified contact procedure for a generic operator request."},
    31: {"status": "AMBIGUOUS", "reason": "The short phrase does not establish whether the user asks where to upload, obtain, or use a power of attorney.", "decision": "CLARIFY"},
    32: {"status": "LABELED", "reason": "Official KB gives the documented escalation path for an unspecified technical error while signing an offer.", "docs": ["zakupki_kb:559611"], "chunks": ["zakupki_kb:559611:0"]},
}


def load_chunk_catalog() -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}
    with CHUNKS.open(encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            catalog[item["chunk_id"]] = item
    return catalog


def validate(rows: list[dict[str, Any]], catalog: dict[str, dict[str, str]]) -> None:
    if len(rows) != len(LABELS):
        raise ValueError(f"Expected {len(LABELS)} source rows, got {len(rows)}")
    all_documents = {item["document_id"] for item in catalog.values()}
    for index, label in LABELS.items():
        for document_id in label.get("docs", []):
            if document_id not in all_documents:
                raise ValueError(f"Unknown document ID at row {index}: {document_id}")
        for chunk_id in label.get("chunks", []):
            item = catalog.get(chunk_id)
            if item is None:
                raise ValueError(f"Unknown chunk ID at row {index}: {chunk_id}")
            if item["document_id"] not in label.get("docs", []):
                raise ValueError(f"Chunk {chunk_id} does not belong to a labeled document at row {index}")
        if label["status"] == "NO_RELEVANT_EVIDENCE" and (label.get("docs") or label.get("chunks")):
            raise ValueError(f"NO_RELEVANT_EVIDENCE must be empty at row {index}")


def candidate_ids(item: dict[str, Any]) -> set[str]:
    return {candidate.get("chunk_id", "") for candidate in item if candidate.get("chunk_id")}


def build_report(rows: list[dict[str, Any]], inspection: dict[str, Any]) -> str:
    counts = Counter(row["silver_label_status"] for row in rows)
    diagnostics = inspection.get("diagnostics", [])
    if len(diagnostics) != len(rows):
        raise ValueError("Inspection result does not align with source rows")
    found = {"bm25": 0, "dense": 0, "hybrid": 0}
    unique = {"bm25": 0, "dense": 0}
    for row, diagnostic in zip(rows, diagnostics, strict=True):
        relevant = set(row["relevant_chunk_ids"])
        if not relevant:
            continue
        hits = {name: bool(relevant & candidate_ids(diagnostic.get(name, []))) for name in found}
        for name, hit in hits.items():
            found[name] += int(hit)
        for name in unique:
            unique[name] += int(hits[name] and not any(hits[other] for other in found if other != name))

    lines = [
        "# Silver labeling report",
        "",
        "> **SILVER / AUTO-LABELED.** These labels were produced by reviewing actual BM25, dense and hybrid candidate unions plus source chunks. They are not human gold labels.",
        "",
        "## Summary",
        "",
        f"- Total queries: {len(rows)}",
        f"- Labeled: {counts['LABELED']}",
        f"- No relevant evidence: {counts['NO_RELEVANT_EVIDENCE']}",
        f"- Ambiguous: {counts['AMBIGUOUS']}",
        f"- Review needed: {counts['REVIEW_NEEDED']}",
        f"- BM25 found a labeled direct chunk: {found['bm25']}",
        f"- Dense found a labeled direct chunk: {found['dense']}",
        f"- Hybrid found a labeled direct chunk: {found['hybrid']}",
        f"- BM25 uniquely found a labeled direct chunk: {unique['bm25']}",
        f"- Dense uniquely found a labeled direct chunk: {unique['dense']}",
        "",
        "Only official KB/manual documents were used as positive labels. Historical tickets were reviewed for troubleshooting context but were not promoted over authoritative evidence.",
        "",
        "## Queries requiring no direct-answer label",
        "",
    ]
    for row in rows:
        if row["silver_label_status"] != "LABELED":
            lines.append(f"- `{row['silver_label_status']}` — **{row['query']}**: {row['silver_label_reason']}")
    changed = [row for row in rows if row.get("silver_expected_decision_changed")]
    lines.extend(["", "## Decision adjustments", ""])
    if changed:
        for row in changed:
            lines.append(f"- **{row['query']}**: `{row['silver_expected_decision_previous']}` → `{row['expected_decision']}` (insufficient context).")
    else:
        lines.append("- None.")
    lines.extend(["", "## Validation", "", "- Every positive document and chunk ID was checked against `all_chunks.jsonl`.", "- Every labeled chunk was checked to belong to its labeled document.", "- `NO_RELEVANT_EVIDENCE`, `AMBIGUOUS`, and `REVIEW_NEEDED` rows retain empty relevance lists."])
    return "\n".join(lines) + "\n"


def main() -> None:
    rows = load_jsonl(SOURCE)
    catalog = load_chunk_catalog()
    validate(rows, catalog)
    labeled_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        label = LABELS[index]
        updated = dict(row)
        updated["relevant_document_ids"] = label.get("docs", [])
        updated["relevant_chunk_ids"] = label.get("chunks", [])
        updated["label_source"] = "codex_silver"
        updated["silver_label_status"] = label["status"]
        updated["silver_label_reason"] = label["reason"]
        if "decision" in label and updated.get("expected_decision") != label["decision"]:
            updated["silver_expected_decision_previous"] = updated.get("expected_decision")
            updated["expected_decision"] = label["decision"]
            updated["silver_expected_decision_changed"] = True
        labeled_rows.append(updated)
    save_jsonl_atomic(OUTPUT, labeled_rows)
    inspection = json.loads(INSPECTION.read_text(encoding="utf-8"))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(build_report(labeled_rows, inspection), encoding="utf-8")
    print(f"Wrote {len(labeled_rows)} SILVER rows to {OUTPUT}")
    print(f"Wrote report to {REPORT}")
    print(dict(sorted(Counter(row['silver_label_status'] for row in labeled_rows).items())))


if __name__ == "__main__":
    main()
