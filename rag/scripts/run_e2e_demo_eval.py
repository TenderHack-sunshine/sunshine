"""Run real Tender Hack RAG demo scenarios and export a reviewable report."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.application.factory import build_rag_service
from src.core.config import Settings
from src.retrieval.official_dense import DenseUnavailable


DEFAULT_SCENARIOS = ROOT / "data" / "eval" / "e2e_demo_scenarios.jsonl"
DEFAULT_JSON = ROOT / "data" / "processed" / "eval" / "e2e_demo_report.json"
DEFAULT_MD = ROOT / "data" / "processed" / "eval" / "e2e_demo_report.md"


class ForcedDenseUnavailable:
    """Controlled demo-only failure; all sparse retrieval remains the real implementation."""

    last_timing = {"query_embedding_ms": 0.0, "dense_search_ms": 0.0}

    def retrieve(self, *_args, **_kwargs):
        raise DenseUnavailable("forced e2e demo dense-unavailable condition")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * fraction), len(ordered) - 1)
    return ordered[index]


def source_review(result: dict) -> tuple[list[dict], list[str]]:
    sources = result.get("sources", [])
    official_indexes = [index for index, source in enumerate(sources) if source.get("authority") == "official"]
    ticket_indexes = [index for index, source in enumerate(sources) if source.get("authority") == "case_history"]
    warnings: list[str] = []
    if result.get("status") == "ANSWER":
        if not sources:
            warnings.append("ANSWER_ZERO_EVIDENCE")
        if not official_indexes:
            warnings.append("ANSWER_ZERO_OFFICIAL_EVIDENCE")
        if ticket_indexes and not official_indexes:
            warnings.append("ANSWER_ONLY_SUPPORT_TICKETS")
        if official_indexes and ticket_indexes and min(ticket_indexes) < min(official_indexes):
            warnings.append("TICKET_PRECEDES_OFFICIAL_EVIDENCE")
    return [
        {key: source.get(key) for key in ("chunk_id", "document_id", "source_type", "authority", "title", "source_path", "section")}
        for source in sources
    ], warnings


def evaluate_scenario(scenario: dict, result: dict, latency_ms: float) -> dict:
    diagnostics = result["diagnostics"]
    evidence, warnings = source_review(result)
    mismatches = []
    expected = scenario
    if expected.get("expected_route") is not None and result.get("route") != expected["expected_route"]:
        mismatches.append(f"route expected {expected['expected_route']}, got {result.get('route')}")
    if expected.get("expected_decision") is not None and result.get("status") != expected["expected_decision"]:
        mismatches.append(f"decision expected {expected['expected_decision']}, got {result.get('status')}")
    if expected.get("expected_retrieval") is not None and diagnostics.get("retrieval_mode") != expected["expected_retrieval"]:
        mismatches.append(f"retrieval expected {expected['expected_retrieval']}, got {diagnostics.get('retrieval_mode')}")
    if expected.get("requires_dense_available") and not diagnostics.get("dense_available"):
        mismatches.append("Dense was required but unavailable")
    if expected.get("requires_bm25_rescue") and not diagnostics.get("bm25_rescue_used"):
        mismatches.append("BM25 rescue was required but not used")
    if expected.get("requires_official_evidence") and not any(source.get("authority") == "official" for source in result.get("sources", [])):
        mismatches.append("Official evidence was required but absent")
    if expected.get("requires_support_ticket") and not any(source.get("authority") == "case_history" for source in result.get("sources", [])):
        mismatches.append("Support-ticket evidence was required but absent")
    if result.get("status") == "ANSWER" and expected.get("expected_decision") in {"NEEDS_CLARIFICATION", "ESCALATE_TO_OPERATOR"}:
        warnings.append("ANSWER_AFTER_EXPECTED_NON_ANSWER")

    structural = "FAIL" if mismatches else "PASS"
    # Retrieval success cannot by itself certify generated answer grounding.
    outcome = "FAIL" if mismatches else "REVIEW" if result.get("status") == "ANSWER" or warnings else "PASS"
    return {
        "id": scenario["id"], "query": scenario["query"], "expected": {key: scenario.get(key) for key in scenario if key != "query"},
        "route": result.get("route"), "decision": result.get("status"), "retrieval_strategy": diagnostics.get("retrieval_strategy"),
        "retrieval_mode": diagnostics.get("retrieval_mode"), "dense_available": diagnostics.get("dense_available"),
        "dense_primary_used": diagnostics.get("dense_primary_used"), "bm25_rescue_used": diagnostics.get("bm25_rescue_used"),
        "bm25_fallback_used": diagnostics.get("bm25_fallback_used"), "profanity_detected": diagnostics.get("profanity_detected"),
        "clarification_policy_triggered": diagnostics.get("clarification_policy_triggered"), "clarification_reason": diagnostics.get("clarification_reason"),
        "official_evidence_present": any(source.get("authority") == "official" for source in result.get("sources", [])),
        "evidence": evidence, "answer": result.get("answer"), "grounding_warnings": warnings, "expectation_mismatches": mismatches,
        "structural_result": structural, "result": outcome, "latency_ms": latency_ms,
        "timings_ms": {**diagnostics.get("timings_ms", {}), "profanity_latency_ms": diagnostics.get("profanity_latency_ms")},
    }


def run_scenarios(service, scenarios: list[dict]) -> list[dict]:
    rows = []
    for scenario in scenarios:
        original_dense = service.retriever.official_dense
        if scenario.get("force_dense_unavailable"):
            service.retriever.official_dense = ForcedDenseUnavailable()
        try:
            started = perf_counter()
            result = service.ask(scenario["query"])
            rows.append(evaluate_scenario(scenario, result, (perf_counter() - started) * 1000))
        finally:
            service.retriever.official_dense = original_dense
    return rows


def latency_summary(rows: list[dict]) -> dict[str, dict[str, float | int | None]]:
    selected = [row for row in rows if row["decision"] == "ANSWER"]
    measures = {"total_ms": [row["latency_ms"] for row in selected]}
    for key in ("profanity_latency_ms", "query_embedding_ms", "dense_search_ms", "bm25_ms", "fusion_ms", "generation_ms"):
        values = []
        for row in selected:
            if key == "profanity_latency_ms":
                value = row["timings_ms"].get(key)
            else:
                value = row["timings_ms"].get(key)
            if isinstance(value, (int, float)):
                values.append(float(value))
        measures[key] = values
    return {name: {"count": len(values), "p50": percentile(values, .5), "p95": percentile(values, .95)} for name, values in measures.items()}


def render_markdown(payload: dict) -> str:
    summary, rows = payload["summary"], payload["scenarios"]
    lines = [
        "# Tender Hack end-to-end demo report", "",
        f"Runtime profanity backend: `{payload['runtime']['profanity_backend']}`; ML E2E: `{payload['runtime']['ml_profanity_e2e']}`. Answers are `REVIEW` until their evidence/answer pairing is manually checked.", "",
        "## Summary", "",
        f"- Total scenarios: **{summary['total']}**", f"- PASS: **{summary['passed']}**", f"- FAIL: **{summary['failed']}**", f"- REVIEW: **{summary['review']}**",
        f"- Grounding warnings: **{summary['grounding_warnings']}**", "",
        "## Compact results", "",
        "| Scenario | Route | Decision | Retrieval | Evidence | Result |", "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        evidence = ", ".join(source.get("source_type") or "unknown" for source in row["evidence"]) or "—"
        lines.append(f"| {row['id']} | {row['route'] or '—'} | {row['decision']} | {row['retrieval_mode']} | {evidence} | {row['result']} |")
    lines += ["", "## Fallback and rescue", ""]
    for row in rows:
        if row["bm25_fallback_used"] or row["bm25_rescue_used"]:
            lines.append(f"- `{row['id']}`: mode={row['retrieval_mode']}, rescue={row['bm25_rescue_used']}, fallback={row['bm25_fallback_used']}")
    lines += ["", "## Grounding review for ANSWER", ""]
    for row in rows:
        if row["decision"] != "ANSWER":
            continue
        lines += [f"### {row['id']}", "", f"**Query:** {row['query']}", "", f"**Answer:** {row['answer']}", "", "**Evidence:**"]
        for source in row["evidence"]:
            lines.append(f"- `{source['chunk_id']}` — {source['source_type']} / {source['authority']} — {source.get('title') or source.get('section') or 'untitled'}")
        if row["grounding_warnings"]:
            lines.append(f"- Warnings: {', '.join(row['grounding_warnings'])}")
        lines.append("")
    lines += ["## Latency (ANSWER scenarios)", "", "| Metric | Count | p50 ms | p95 ms |", "| --- | ---: | ---: | ---: |"]
    for name, values in payload["latency"].items():
        p50 = "—" if values["p50"] is None else f"{values['p50']:.1f}"
        p95 = "—" if values["p95"] is None else f"{values['p95']:.1f}"
        lines.append(f"| {name} | {values['count']} | {p50} | {p95} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run end-to-end demo scenarios against the actual RAG pipeline.")
    parser.add_argument("scenarios", type=Path, nargs="?", default=DEFAULT_SCENARIOS)
    parser.add_argument("--output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MD)
    parser.add_argument("--profanity-backend", choices=("rule", "deterministic"), help="Explicit runtime backend.")
    args = parser.parse_args()
    kwargs = {"profanity_backend": args.profanity_backend} if args.profanity_backend else {}
    settings = Settings(**kwargs)
    service = build_rag_service(settings)
    rows = run_scenarios(service, load_jsonl(args.scenarios))
    summary = {"total": len(rows), "passed": sum(row["result"] == "PASS" for row in rows), "failed": sum(row["result"] == "FAIL" for row in rows),
               "review": sum(row["result"] == "REVIEW" for row in rows), "grounding_warnings": sum(len(row["grounding_warnings"]) for row in rows),
               "decision_errors": sum(bool(row["expectation_mismatches"]) for row in rows)}
    payload = {"runtime": {"profanity_backend": settings.profanity_backend, "ml_profanity_e2e": "RETIRED_DETERMINISTIC_RULES",
                            "retrieval_strategy": settings.retrieval_strategy, "reranker_enabled": settings.rerank_enabled,
                            "confidence_min_official_score": settings.confidence_min_official_score},
               "summary": summary, "scenarios": rows, "latency": latency_summary(rows)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.markdown.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    print(f"Saved: {args.output}")
    print(f"Saved: {args.markdown}")


if __name__ == "__main__":
    main()
