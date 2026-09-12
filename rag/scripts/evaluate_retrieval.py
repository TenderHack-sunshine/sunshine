from __future__ import annotations

"""Offline labelled retrieval evaluation; does not depend on answer generation."""

import argparse
import json
import statistics
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.application.factory import build_rag_service
from src.core.config import Settings
from src.retrieval.mvp import rrf_fuse

SYSTEMS = ("BM25", "DENSE", "HYBRID", "HYBRID_RERANKED")
K_VALUES = (1, 3, 5, 10)
DECISION_ALIASES = {"CLARIFY": "NEEDS_CLARIFICATION", "ESCALATE": "ESCALATE_TO_OPERATOR", "REFUSE_PROFANITY": "REFUSE_PROFANITY"}


def normalized_decision(value: str | None) -> str | None:
    return DECISION_ALIASES.get(value, value)


def load_cases(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix.lower() == ".json":
        value = json.loads(text)
        return value if isinstance(value, list) else [value]
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def is_relevant(result: dict, case: dict) -> bool:
    chunk_ids = set(case.get("relevant_chunk_ids") or [])
    document_ids = set(case.get("relevant_document_ids") or [])
    return bool((chunk_ids and result.get("chunk_id") in chunk_ids) or (document_ids and result.get("document_id") in document_ids))


def is_relevant_level(result: dict, case: dict, level: str) -> bool:
    key = "relevant_chunk_ids" if level == "chunk" else "relevant_document_ids"
    result_key = "chunk_id" if level == "chunk" else "document_id"
    return result.get(result_key) in set(case.get(key) or [])


def metric_summary(rankings: list[tuple[dict, list[dict]]]) -> dict:
    labelled = [(case, results) for case, results in rankings if case.get("relevant_chunk_ids") or case.get("relevant_document_ids")]
    summary = {"labelled_queries": len(labelled)}
    for k in K_VALUES:
        hits = [any(is_relevant(item, case) for item in results[:k]) for case, results in labelled]
        value = sum(hits) / len(hits) if hits else None
        summary[f"recall_at_{k}"] = value
        summary[f"hit_rate_at_{k}"] = value
    reciprocal = []
    for case, results in labelled:
        rank = next((index for index, item in enumerate(results[:10], 1) if is_relevant(item, case)), None)
        reciprocal.append(1 / rank if rank else 0.0)
    summary["mrr_at_10"] = sum(reciprocal) / len(reciprocal) if reciprocal else None
    return summary


def metric_summary_level(rankings: list[tuple[dict, list[dict]]], level: str) -> dict:
    key = "relevant_chunk_ids" if level == "chunk" else "relevant_document_ids"
    labelled = [(case, results) for case, results in rankings if case.get(key)]
    summary = {"labelled_queries": len(labelled)}
    for k in K_VALUES:
        hits = [any(is_relevant_level(item, case, level) for item in results[:k]) for case, results in labelled]
        value = sum(hits) / len(hits) if hits else None
        summary[f"recall_at_{k}"] = value
        summary[f"hit_rate_at_{k}"] = value
    reciprocal = []
    for case, results in labelled:
        rank = next((index for index, item in enumerate(results[:10], 1) if is_relevant_level(item, case, level)), None)
        reciprocal.append(1 / rank if rank else 0.0)
    summary["mrr_at_10"] = sum(reciprocal) / len(reciprocal) if reciprocal else None
    return summary


def grouped_metrics(rankings: dict[str, list[tuple[dict, list[dict]]]], field: str) -> dict:
    values = sorted({case.get(field) for entries in rankings.values() for case, _ in entries if case.get(field)})
    return {value: {name: {"chunk": metric_summary_level([(case, result) for case, result in entries if case.get(field) == value], "chunk"),
                           "document": metric_summary_level([(case, result) for case, result in entries if case.get(field) == value], "document")}
                    for name, entries in rankings.items()} for value in values}


def accuracy(rows: list[tuple[str | None, str | None]]) -> dict:
    labelled = [(expected, actual) for expected, actual in rows if expected]
    correct = sum(expected == actual for expected, actual in labelled)
    confusion: dict[str, dict[str, int]] = {}
    for expected, actual in labelled:
        confusion.setdefault(str(expected), {})[str(actual)] = confusion.setdefault(str(expected), {}).get(str(actual), 0) + 1
    return {"labelled_queries": len(labelled), "accuracy": correct / len(labelled) if labelled else None, "confusion": confusion}


def _case_hit(results: list[dict], case: dict) -> bool | None:
    level = "chunk" if case.get("relevant_chunk_ids") else "document" if case.get("relevant_document_ids") else None
    return any(is_relevant_level(item, case, level) for item in results[:10]) if level else None


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def compact(result: dict) -> dict:
    output = {key: result.get(key) for key in ("chunk_id", "document_id", "source_type", "authority", "rank", "raw_score", "rrf_score", "reranker_score", "title", "section")}
    output["text_preview"] = " ".join(str(result.get("text", "")).split())[:320]
    return output


def evaluate(cases: list[dict], service, rerank: bool = False, end_to_end: bool = True) -> dict:
    rankings = {name: [] for name in SYSTEMS}
    diagnostics = []
    routing_rows, decision_rows = [], []
    latencies: dict[str, list[float]] = {"bm25_ms": [], "dense_ms": [], "rrf_ms": [], "reranker_ms": [], "total_ms": []}
    for case in cases:
        query = case["query"]
        predicted_route = service.router.classify(query)["route"]
        expected_route = case.get("expected_route", case.get("route"))
        route = expected_route or predicted_route
        started = perf_counter()
        trace = service.retriever.retrieve_with_trace(query, technical=route == "L3", top_k=20)
        bm25_lists = [trace.get("official_bm25", [])]
        if route == "L3":
            bm25_lists.append(trace.get("ticket_bm25", []))
        bm25 = rrf_fuse(bm25_lists, k=service.retriever.rrf_k) if bm25_lists else []
        dense = trace.get("official_dense", [])
        hybrid = trace.get("fused", [])
        reranked = hybrid
        reranker_error = None
        reranker_started = perf_counter()
        if rerank and getattr(service.reranker, "available", False):
            try:
                reranked = service.reranker.rerank(query, hybrid[:service.rerank_top_n], service.final_top_k)
            except Exception as error:
                reranker_error = str(error)
        reranker_ms = (perf_counter() - reranker_started) * 1000 if rerank else 0.0
        systems = {"BM25": bm25, "DENSE": dense, "HYBRID": hybrid, "HYBRID_RERANKED": reranked}
        for name, results in systems.items():
            rankings[name].append((case, results))
        timing = trace.get("timing", {})
        latencies["bm25_ms"].append(float(timing.get("bm25_ms", 0.0)))
        latencies["dense_ms"].append(float(timing.get("query_embedding_ms", 0.0)) + float(timing.get("dense_search_ms", 0.0)))
        latencies["rrf_ms"].append(float(timing.get("fusion_ms", 0.0)))
        latencies["reranker_ms"].append(reranker_ms)
        latencies["total_ms"].append((perf_counter() - started) * 1000)
        app = service.ask(query) if end_to_end else None
        routing_rows.append((expected_route, predicted_route))
        decision_rows.append((normalized_decision(case.get("expected_decision")), app.get("status") if app else None))
        groundedness = {"answer_produced": bool(app and app.get("status") == "ANSWER"), "official_evidence_present": bool(app and any(source.get("authority") == "official" for source in app.get("sources", []))),
                        "ticket_evidence_present": bool(app and any(source.get("authority") == "case_history" for source in app.get("sources", []))),
                        "evidence_ids": [source.get("chunk_id") for source in app.get("sources", [])] if app else [],
                        "flag_answer_without_official": bool(app and app.get("status") == "ANSWER" and not any(source.get("authority") == "official" for source in app.get("sources", []))),
                        "flag_answer_without_evidence": bool(app and app.get("status") == "ANSWER" and not app.get("sources"))}
        diagnostics.append({"query": query, "route": route, "predicted_route": predicted_route, "expected": {key: case.get(key) for key in ("relevant_chunk_ids", "relevant_document_ids", "expected_decision", "notes", "category", "difficulty", "answer_requirements")},
                            "bm25": [compact(item) for item in bm25], "dense": [compact(item) for item in dense],
                            "hybrid": [compact(item) for item in hybrid], "reranked": [compact(item) for item in reranked],
                            "hit_at_5": any(is_relevant(item, case) for item in hybrid[:5]), "reranker_error": reranker_error,
                            "timing_ms": timing, "actual_decision": app.get("status") if app else None, "groundedness": groundedness,
                            "confidence": app.get("diagnostics", {}).get("confidence") if app else None})
    metrics = {name: {"chunk": metric_summary_level(values, "chunk"), "document": metric_summary_level(values, "document")} for name, values in rankings.items()}
    by_route = grouped_metrics(rankings, "expected_route")
    if not by_route:
        # Existing datasets use ``route``; preserve that schema.
        by_route = grouped_metrics(rankings, "route")
    by_category = grouped_metrics(rankings, "category")
    failures = []
    comparisons = {"hybrid_improved_over_bm25": 0, "hybrid_regressed_vs_bm25": 0, "dense_rescued_bm25_failure": 0,
                   "bm25_rescued_dense_failure": 0, "reranker_improved": 0, "reranker_regressed": 0, "all_retrievers_failed": 0}
    for case_index, row in enumerate(diagnostics):
        hits = {name: _case_hit(results[case_index][1], cases[case_index]) for name, results in rankings.items()}
        if hits["BM25"] is None:
            continue
        if hits["HYBRID"] and not hits["BM25"]:
            comparisons["hybrid_improved_over_bm25"] += 1
        if hits["BM25"] and not hits["HYBRID"]:
            comparisons["hybrid_regressed_vs_bm25"] += 1
        if hits["DENSE"] and not hits["BM25"]:
            comparisons["dense_rescued_bm25_failure"] += 1
        if hits["BM25"] and not hits["DENSE"]:
            comparisons["bm25_rescued_dense_failure"] += 1
        if hits["HYBRID_RERANKED"] and not hits["HYBRID"]:
            comparisons["reranker_improved"] += 1
        if hits["HYBRID"] and not hits["HYBRID_RERANKED"]:
            comparisons["reranker_regressed"] += 1
        if not any(hits.values()):
            comparisons["all_retrievers_failed"] += 1
        if len(set(hits.values())) > 1 or not any(hits.values()):
            failures.append({"query": row["query"], "hits_at_10": hits})
    latency_report = {name: {"p50": percentile(values, .5), "p95": percentile(values, .95)} for name, values in latencies.items()}
    dangerous = [row["query"] for row in diagnostics if normalized_decision(row["expected"].get("expected_decision")) == "ESCALATE_TO_OPERATOR" and row.get("actual_decision") == "ANSWER"]
    return {"metrics": metrics, "by_route": by_route, "by_category": by_category, "routing": accuracy(routing_rows), "decisions": accuracy(decision_rows),
            "latency_ms": latency_report, "diagnostics": diagnostics, "failure_analysis": failures, "dangerous_decision_cases": dangerous, "comparison": comparisons}


def _fmt(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def markdown_report(report: dict) -> str:
    lines = ["# Tender Hack retrieval evaluation", "", "## Retrieval metrics", "", "| System | Label level | R@1 | R@3 | R@5 | R@10 | MRR@10 | Labels |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name, levels in report["metrics"].items():
        for level, values in levels.items():
            lines.append(f"| {name} | {level} | {_fmt(values['recall_at_1'])} | {_fmt(values['recall_at_3'])} | {_fmt(values['recall_at_5'])} | {_fmt(values['recall_at_10'])} | {_fmt(values['mrr_at_10'])} | {values['labelled_queries']} |")
    lines += ["", "## Routing and decisions", "", f"- Route accuracy: {_fmt(report['routing']['accuracy'])} ({report['routing']['labelled_queries']} labels)", f"- Decision accuracy: {_fmt(report['decisions']['accuracy'])} ({report['decisions']['labelled_queries']} labels)", "", "## Retrieval comparison", ""]
    lines += [f"- {key.replace('_', ' ')}: {value}" for key, value in report["comparison"].items()]
    lines += ["", "## Latency (ms, p50/p95)", ""]
    lines += [f"- {name}: {_fmt(values['p50'])} / {_fmt(values['p95'])}" for name, values in report["latency_ms"].items()]
    lines += ["", f"## Manual review\n\nFailure-analysis cases: {len(report['failure_analysis'])}", f"Dangerous expected-escalate / actual-answer cases: {len(report.get('dangerous_decision_cases', []))}"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate BM25, dense, hybrid and optional reranked retrieval against JSONL labels.")
    parser.add_argument("dataset", type=Path, nargs="?", default=Path("data/eval/retrieval_eval.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/eval/retrieval_eval_report.json"))
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument("--limit", type=int, help="Evaluate only the first N rows; useful for a quick dry run.")
    args = parser.parse_args()
    service = build_rag_service(Settings())
    cases = load_cases(args.dataset)
    if args.limit is not None:
        cases = cases[:args.limit]
    report = evaluate(cases, service, rerank=args.rerank)
    print("SYSTEM             LEVEL     R@1    R@3    R@5    R@10   MRR@10  labels")
    for name, levels in report["metrics"].items():
        for level, values in levels.items():
            print(f"{name:<18} {level:<9} {_fmt(values['recall_at_1']):<6} {_fmt(values['recall_at_3']):<6} {_fmt(values['recall_at_5']):<6} {_fmt(values['recall_at_10']):<6} {_fmt(values['mrr_at_10']):<7} {values['labelled_queries']}")
    print("Latency ms (p50/p95): " + ", ".join(f"{name}={_fmt(data['p50'])}/{_fmt(data['p95'])}" for name, data in report["latency_ms"].items()))
    print(f"Route accuracy: {_fmt(report['routing']['accuracy'])} ({report['routing']['labelled_queries']} labels); Decision accuracy: {_fmt(report['decisions']['accuracy'])} ({report['decisions']['labelled_queries']} labels)")
    print(f"Failure-analysis cases: {len(report['failure_analysis'])}")
    print("Comparison: " + ", ".join(f"{key}={value}" for key, value in report["comparison"].items()))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved: {args.output}")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown_report(report), encoding="utf-8")
        print(f"Saved: {args.markdown}")


if __name__ == "__main__":
    main()
