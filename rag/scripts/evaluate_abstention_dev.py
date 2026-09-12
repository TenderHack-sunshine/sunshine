from __future__ import annotations

"""Evaluate abstention policy on MODEL_REVIEWED DEV labels only.

This script deliberately refuses FINAL input and records label provenance in
every report. It does not write to the input dataset.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.application.factory import build_rag_service
from src.core.config import Settings


DEFAULT_INPUT = ROOT / "data/eval/abstention_calibration_dev_reviewed.jsonl"
DEFAULT_OUTPUT = ROOT / "data/processed/eval/abstention_dev_evidence_sufficiency.json"
DEFAULT_MARKDOWN = ROOT / "data/processed/eval/abstention_dev_evidence_sufficiency.md"
_EXACT_FACT = re.compile(r"\b(?:сколько|сумм[ауые]|размер|процент|комисси[яиюе]|штраф|срок)\b", re.IGNORECASE)
_NAVIGATION = re.compile(r"\b(?:где|куда|меню|раздел|скачать|посмотреть|найти)\b", re.IGNORECASE)


def load(path: Path) -> list[dict]:
    if "final" in path.name.lower():
        raise ValueError("FINAL input is forbidden in DEV evaluator")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not rows or any(row.get("review_status") != "MODEL_REVIEWED" for row in rows):
        raise ValueError("every DEV row must be explicitly MODEL_REVIEWED")
    if any(row.get("label") not in {"ANSWERABLE", "INSUFFICIENT_KNOWLEDGE", "AMBIGUOUS_QUERY"} for row in rows):
        raise ValueError("DEV rows need a supported provisional label")
    return rows


def dimensions(row: dict) -> set[str]:
    labels = {row["category"]}
    if row.get("gap_type") == "PARTIAL_KNOWLEDGE":
        labels.add("partial_knowledge")
    if row.get("gap_type") == "NO_RELEVANT_DOCUMENTS":
        labels.add("no_relevant_documents")
    if row["label"] == "AMBIGUOUS_QUERY":
        labels.add("ambiguous")
    if _EXACT_FACT.search(row["query"]):
        labels.add("exact_fact")
    if _NAVIGATION.search(row["query"]):
        labels.add("navigation")
    return labels


def grounding(result: dict) -> dict:
    sources = result.get("sources", [])
    official = any(item.get("authority") == "official" for item in sources)
    return {
        "answer_produced": result["status"] == "ANSWER",
        "official_evidence_present": official,
        "answer_without_official": result["status"] == "ANSWER" and not official,
        "grounding_violation": result["status"] == "ANSWER" and not sources,
    }


def outcome(label: str, status: str) -> str:
    if label == "ANSWERABLE":
        return "ANSWERED" if status == "ANSWER" else "FALSE_ESCALATION"
    if label == "INSUFFICIENT_KNOWLEDGE":
        return "SAFE_ESCALATION" if status == "ESCALATE_TO_OPERATOR" else "DANGEROUS_ANSWER" if status == "ANSWER" else "OTHER_ABSTENTION"
    return "SAFE_AMBIGUITY_HANDLING" if status in {"NEEDS_CLARIFICATION", "ESCALATE_TO_OPERATOR"} else "INCORRECT_ANSWER"


def evaluate(rows: list[dict]) -> list[dict]:
    settings = Settings(evidence_sufficiency_enabled=True)
    service = build_rag_service(settings)
    output = []
    for row in rows:
        started = perf_counter()
        result = service.ask(row["query"])
        diagnostics = result["diagnostics"]
        output.append({
            "id": row["id"], "query": row["query"], "label": row["label"], "gap_type": row.get("gap_type"),
            "review_status": "MODEL_REVIEWED", "category": row["category"], "dimensions": sorted(dimensions(row)),
            "actual_status": result["status"], "outcome": outcome(row["label"], result["status"]),
            "answer": result["answer"], "sources": result.get("sources", []),
            "dense_score": diagnostics.get("confidence", {}).get("dense_top_score"),
            "bm25_score": diagnostics.get("confidence", {}).get("bm25_top_score"),
            "evidence_sufficiency": diagnostics.get("evidence_sufficiency"),
            "knowledge_gap": diagnostics.get("knowledge_gap", {}).get("classification"),
            "grounding": grounding(result), "confidence_reason": diagnostics.get("confidence_reason"),
            "latency_ms": (perf_counter() - started) * 1000,
        })
    return output


def metrics(records: list[dict]) -> dict:
    labels: dict[str, list[dict]] = defaultdict(list)
    for row in records:
        labels[row["label"]].append(row)
    answerable = labels["ANSWERABLE"]
    insufficient = labels["INSUFFICIENT_KNOWLEDGE"]
    ambiguous = labels["AMBIGUOUS_QUERY"]
    return {
        "ANSWERABLE": {"total": len(answerable), "answered": sum(x["outcome"] == "ANSWERED" for x in answerable),
                       "false_escalations": sum(x["outcome"] == "FALSE_ESCALATION" for x in answerable),
                       "acceptance_rate": sum(x["outcome"] == "ANSWERED" for x in answerable) / max(len(answerable), 1)},
        "INSUFFICIENT_KNOWLEDGE": {"total": len(insufficient), "safely_escalated": sum(x["outcome"] == "SAFE_ESCALATION" for x in insufficient),
                                     "dangerously_answered": sum(x["outcome"] == "DANGEROUS_ANSWER" for x in insufficient),
                                     "safe_rejection_rate": sum(x["outcome"] == "SAFE_ESCALATION" for x in insufficient) / max(len(insufficient), 1)},
        "AMBIGUOUS_QUERY": {"total": len(ambiguous), "safely_handled": sum(x["outcome"] == "SAFE_AMBIGUITY_HANDLING" for x in ambiguous),
                            "incorrectly_answered": sum(x["outcome"] == "INCORRECT_ANSWER" for x in ambiguous)},
    }


def breakdown(records: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in records:
        for dimension in row["dimensions"]:
            grouped[dimension].append(row)
    return {name: {"total": len(rows), "outcomes": dict(Counter(row["outcome"] for row in rows))} for name, rows in sorted(grouped.items())}


def root_cause(row: dict) -> str:
    sufficiency = row.get("evidence_sufficiency") or {}
    if sufficiency.get("reason") == "SUPPORTED_BY_EXTRACTIVE_EVIDENCE":
        return "evidence_sufficiency_false_negative: topical evidence passed without supporting the requested claim"
    if sufficiency.get("reason") == "DISABLED":
        return "configuration_error: evidence sufficiency was not enabled"
    return "unexpected_policy_path: inspect confidence and evidence diagnostics"


def markdown(payload: dict) -> str:
    lines = ["# DEV abstention safety evaluation", "", "> Labels are **MODEL_REVIEWED provisional development labels**, not HUMAN_REVIEWED labels. FINAL was not read or evaluated.", "",
             "## Metrics", "", "```json", json.dumps(payload["metrics"], ensure_ascii=False, indent=2), "```", "",
             "## Breakdown", "", "| Dimension | Total | Outcomes |", "| --- | ---: | --- |"]
    for name, values in payload["breakdown"].items():
        lines.append(f"| {name} | {values['total']} | {values['outcomes']} |")
    dangers = [row for row in payload["records"] if row["outcome"] == "DANGEROUS_ANSWER"]
    lines += ["", f"## Dangerous false answers ({len(dangers)})", ""]
    for row in dangers:
        lines += [f"### {row['id']}", "", f"- Query: {row['query']}", f"- Expected label: `{row['label']}`", f"- Actual status: `{row['actual_status']}`", f"- Generated answer: {row['answer']}",
                  f"- Retrieved chunks: {', '.join('`' + str(item.get('chunk_id')) + '`' for item in row['sources']) or 'none'}",
                  f"- Dense score: {row['dense_score']}; BM25 score: {row['bm25_score']}", f"- Evidence sufficiency: {row['evidence_sufficiency']}",
                  f"- Knowledge gap: {row['knowledge_gap']}", f"- Grounding: {row['grounding']}", f"- Root cause: {root_cause(row)}", ""]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    records = evaluate(load(args.input))
    payload = {"label_provenance": "MODEL_REVIEWED_PROVISIONAL", "evidence_sufficiency_enabled": True,
               "input": str(args.input), "metrics": metrics(records), "breakdown": breakdown(records), "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.markdown.write_text(markdown(payload), encoding="utf-8")
    print(json.dumps(payload["metrics"], ensure_ascii=False))
    print(f"Saved: {args.output}\nSaved: {args.markdown}")


if __name__ == "__main__":
    main()
