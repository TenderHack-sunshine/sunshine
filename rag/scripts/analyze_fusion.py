"""Analyze dense/BM25 fusion and sweep weighted RRF without a model sweep.

The script uses the saved silver evaluation report for baseline regression
diagnostics.  It obtains each query's candidate lists once, then re-fuses those
fixed candidates offline for every configuration.  Thus weights are compared
fairly without repeatedly embedding the same 33 queries.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.application.factory import build_rag_service
from src.core.config import Settings
from src.retrieval.mvp import rrf_fuse


DEFAULT_DATASET = ROOT / "data" / "eval" / "retrieval_eval_silver.jsonl"
DEFAULT_REPORT = ROOT / "data" / "processed" / "eval" / "retrieval_eval_silver_report.json"
DEFAULT_REGRESSIONS = ROOT / "data" / "processed" / "eval" / "hybrid_regression_analysis.md"
DEFAULT_SWEEP_JSON = ROOT / "data" / "processed" / "eval" / "fusion_sweep.json"
DEFAULT_SWEEP_MD = ROOT / "data" / "processed" / "eval" / "fusion_sweep.md"
K_VALUES = (1, 3, 5, 10)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def first_document_rank(results: list[dict[str, Any]], document_id: str) -> int | None:
    return next((rank for rank, result in enumerate(results, 1) if result.get("document_id") == document_id), None)


def first_document_result(results: list[dict[str, Any]], document_id: str) -> tuple[int | None, dict[str, Any] | None]:
    rank = first_document_rank(results, document_id)
    return (rank, results[rank - 1]) if rank is not None else (None, None)


def document_metrics(rankings: list[tuple[dict[str, Any], list[dict[str, Any]]]]) -> dict[str, float | int | None]:
    labelled = [(case, results) for case, results in rankings if case.get("relevant_document_ids")]
    output: dict[str, float | int | None] = {"labelled_queries": len(labelled)}
    first_ranks: list[int | None] = []
    for case, results in labelled:
        ranks = [first_document_rank(results, document_id) for document_id in case["relevant_document_ids"]]
        first_ranks.append(min((rank for rank in ranks if rank is not None), default=None))
    for k in K_VALUES:
        output[f"recall_at_{k}"] = sum(rank is not None and rank <= k for rank in first_ranks) / len(first_ranks) if first_ranks else None
    output["mrr_at_10"] = sum(1 / rank if rank is not None and rank <= 10 else 0 for rank in first_ranks) / len(first_ranks) if first_ranks else None
    return output


def compact_displacer(result: dict[str, Any], rank: int, dense: list[dict[str, Any]], bm25: list[dict[str, Any]]) -> dict[str, Any]:
    dense_rank, dense_item = first_document_result(dense, str(result.get("document_id")))
    bm25_rank, bm25_item = first_document_result(bm25, str(result.get("document_id")))
    return {
        "hybrid_rank": rank,
        "document_id": result.get("document_id"),
        "chunk_id": result.get("chunk_id"),
        "title": result.get("title") or result.get("section") or "(untitled)",
        "source_type": result.get("source_type"),
        "dense_rank": dense_rank,
        "dense_score": dense_item.get("raw_score") if dense_item else None,
        "bm25_rank": bm25_rank,
        "bm25_score": bm25_item.get("raw_score") if bm25_item else None,
        "rrf_score": result.get("rrf_score"),
    }


def build_regression_rows(cases: list[dict[str, Any]], report: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics = report.get("diagnostics", [])
    if len(cases) != len(diagnostics):
        raise ValueError("Silver dataset and evaluation diagnostics must contain the same number of rows")
    regressions: list[dict[str, Any]] = []
    for case, diagnostic in zip(cases, diagnostics, strict=True):
        dense, bm25, hybrid = diagnostic.get("dense", []), diagnostic.get("bm25", []), diagnostic.get("hybrid", [])
        for document_id in case.get("relevant_document_ids", []):
            dense_rank, dense_item = first_document_result(dense, document_id)
            hybrid_rank, hybrid_item = first_document_result(hybrid, document_id)
            if dense_rank is None or (hybrid_rank is not None and hybrid_rank <= dense_rank):
                continue
            displaced = []
            seen_documents = {document_id}
            for rank, candidate in enumerate(hybrid, 1):
                if hybrid_rank is not None and rank >= hybrid_rank:
                    break
                candidate_document_id = candidate.get("document_id")
                if candidate_document_id not in seen_documents:
                    displaced.append(compact_displacer(candidate, rank, dense, bm25))
                    seen_documents.add(candidate_document_id)
            bm25_rank, bm25_item = first_document_result(bm25, document_id)
            regressions.append({
                "query": case["query"], "relevant_document_id": document_id,
                "dense_rank": dense_rank, "bm25_rank": bm25_rank,
                "hybrid_rank": hybrid_rank, "dense_score": dense_item.get("raw_score") if dense_item else None,
                "bm25_score": bm25_item.get("raw_score") if bm25_item else None,
                "rrf_score": hybrid_item.get("rrf_score") if hybrid_item else None,
                "displaced_by": displaced,
            })
    return regressions


def complementarity(cases: list[dict[str, Any]], report: dict[str, Any]) -> dict[str, dict[str, int]]:
    totals = {str(k): Counter() for k in K_VALUES}
    for case, diagnostic in zip(cases, report["diagnostics"], strict=True):
        documents = case.get("relevant_document_ids", [])
        if not documents:
            continue
        for k in K_VALUES:
            dense_hit = any(first_document_rank(diagnostic.get("dense", [])[:k], document_id) for document_id in documents)
            bm25_hit = any(first_document_rank(diagnostic.get("bm25", [])[:k], document_id) for document_id in documents)
            bucket = "both_succeed" if dense_hit and bm25_hit else "dense_only" if dense_hit else "bm25_only" if bm25_hit else "both_fail"
            totals[str(k)][bucket] += 1
    return {key: {name: values[name] for name in ("both_succeed", "dense_only", "bm25_only", "both_fail")} for key, values in totals.items()}


def markdown_regressions(rows: list[dict[str, Any]], counts: dict[str, dict[str, int]]) -> str:
    lines = [
        "# Hybrid regression analysis",
        "",
        "> **SILVER evaluation only.** Ranks are document-level and use the existing equal-weight RRF report. Raw BM25 and dense scores are shown for inspection but are never directly compared.",
        "",
        f"Relevant document regressions (HYBRID worse than DENSE): **{len(rows)}**.",
        "",
        "## BM25 / Dense complementarity",
        "",
        "| @k | Both succeed | Dense only | BM25 only | Both fail |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for k, values in counts.items():
        lines.append(f"| {k} | {values['both_succeed']} | {values['dense_only']} | {values['bm25_only']} | {values['both_fail']} |")
    lines += ["", "## Regressions", ""]
    if not rows:
        lines.append("No dense-to-hybrid document-rank regressions were found.")
    for row in rows:
        lines.extend([
            f"### {row['query']} — `{row['relevant_document_id']}`",
            "",
            f"- Dense rank / score: `{row['dense_rank']}` / `{row['dense_score']}`",
            f"- BM25 rank / score: `{row['bm25_rank']}` / `{row['bm25_score']}`",
            f"- Hybrid rank / RRF score: `{row['hybrid_rank']}` / `{row['rrf_score']}`",
            "- Documents ahead in HYBRID:",
        ])
        for result in row["displaced_by"]:
            lines.append(f"  - #{result['hybrid_rank']} `{result['document_id']}` ({result['source_type']}; dense #{result['dense_rank']}, BM25 #{result['bm25_rank']}, RRF {result['rrf_score']}): {result['title']}")
        if not row["displaced_by"]:
            lines.append("  - Not returned in the recorded HYBRID candidate list.")
        lines.append("")
    return "\n".join(lines)


def candidate_lists(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retrieve each union once; all sweep configurations then run locally."""
    settings = Settings(bm25_top_k=20, dense_top_k=20, rerank_enabled=False)
    service = build_rag_service(settings)
    collected = []
    for index, case in enumerate(cases, 1):
        route = case.get("expected_route", case.get("route"))
        trace = service.retriever.retrieve_with_trace(case["query"], technical=route == "L3", top_k=20)
        if not trace.get("dense_available"):
            raise RuntimeError(f"Dense retrieval unavailable for query {index}: {trace.get('dense_error')}")
        collected.append({"official_bm25": trace["official_bm25"], "dense": trace["official_dense"], "tickets": trace["ticket_bm25"]})
        print(f"[{index}/{len(cases)}] candidates collected")
    return collected


def fused_results(inputs: dict[str, Any], bm25_top_k: int, rrf_k: int, dense_weight: float, bm25_weight: float) -> list[dict[str, Any]]:
    lists = [inputs["official_bm25"][:bm25_top_k], inputs["dense"]]
    weights = [bm25_weight, dense_weight]
    if inputs["tickets"]:
        lists.append(inputs["tickets"])
        weights.append(bm25_weight)
    return rrf_fuse(lists, k=rrf_k, weights=weights)


def make_sweep(cases: list[dict[str, Any]], inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    bm25_rankings = []
    dense_rankings = []
    for case, item in zip(cases, inputs, strict=True):
        sparse_lists = [item["official_bm25"]]
        if item["tickets"]:
            sparse_lists.append(item["tickets"])
        bm25_rankings.append((case, rrf_fuse(sparse_lists, k=60)))
        dense_rankings.append((case, item["dense"]))
    for name, rankings, config in (("BM25", bm25_rankings, None), ("Dense", dense_rankings, None)):
        metrics = document_metrics(rankings)
        rows.append({"name": name, "configuration": config, "metrics": metrics, "regression_count_vs_dense": 0})
    for bm25_top_k in (10, 20):
        for rrf_k in (20, 40, 60):
            for dense_weight in (1.0, 1.25, 1.5, 2.0):
                for bm25_weight in (0.5, 0.75, 1.0):
                    rankings = [(case, fused_results(item, bm25_top_k, rrf_k, dense_weight, bm25_weight)) for case, item in zip(cases, inputs, strict=True)]
                    metrics = document_metrics(rankings)
                    regressions = 0
                    for case, item, (_, fused) in zip(cases, inputs, rankings, strict=True):
                        if not case.get("relevant_document_ids"):
                            continue
                        dense_rank = min((first_document_rank(item["dense"], document_id) for document_id in case["relevant_document_ids"] if first_document_rank(item["dense"], document_id) is not None), default=None)
                        fused_rank = min((first_document_rank(fused, document_id) for document_id in case["relevant_document_ids"] if first_document_rank(fused, document_id) is not None), default=None)
                        regressions += int(dense_rank is not None and (fused_rank is None or fused_rank > dense_rank))
                    rows.append({"name": "Weighted RRF", "configuration": {"bm25_top_k": bm25_top_k, "rrf_k": rrf_k, "dense_weight": dense_weight, "bm25_weight": bm25_weight}, "metrics": metrics, "regression_count_vs_dense": regressions})
    return rows


def config_label(row: dict[str, Any]) -> str:
    config = row["configuration"]
    if config is None:
        return row["name"]
    return f"RRF d={config['dense_weight']:g} / b={config['bm25_weight']:g}; k={config['rrf_k']}; BM25@{config['bm25_top_k']}"


def best_configuration(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    dense = next(row for row in rows if row["name"] == "Dense")["metrics"]
    original = next(row for row in rows if row["configuration"] == {"bm25_top_k": 20, "rrf_k": 60, "dense_weight": 1.0, "bm25_weight": 1.0})["metrics"]
    eligible = [
        row for row in rows if row["configuration"] is not None
        and row["metrics"]["recall_at_5"] >= dense["recall_at_5"]
        and row["metrics"]["recall_at_10"] >= original["recall_at_10"]
        and row["metrics"]["mrr_at_10"] >= dense["mrr_at_10"] - 0.02
    ]
    return max(eligible, key=lambda row: (row["metrics"]["mrr_at_10"], row["metrics"]["recall_at_5"], row["metrics"]["recall_at_10"], -row["regression_count_vs_dense"])) if eligible else None


def best_observed_configuration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [row for row in rows if row["configuration"] is not None]
    return max(candidates, key=lambda row: (row["metrics"]["recall_at_5"], row["metrics"]["mrr_at_10"], row["metrics"]["recall_at_10"], -row["regression_count_vs_dense"]))


def markdown_sweep(rows: list[dict[str, Any]], best: dict[str, Any] | None, observed: dict[str, Any]) -> str:
    lines = [
        "# Weighted RRF fusion sweep",
        "",
        "> **SILVER evaluation only (15 document-level positive labels).** Candidate lists were retrieved once, then every configuration below was fused offline. Reranking was disabled.",
        "",
        "| Configuration | R@1 | R@3 | R@5 | R@10 | MRR@10 | Dense-rank regressions |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        metrics = row["metrics"]
        lines.append(f"| {config_label(row)} | {metrics['recall_at_1']:.3f} | {metrics['recall_at_3']:.3f} | {metrics['recall_at_5']:.3f} | {metrics['recall_at_10']:.3f} | {metrics['mrr_at_10']:.3f} | {row['regression_count_vs_dense']} |")
    lines += ["", "## Recommendation", ""]
    if best:
        lines.append(f"Best eligible weighted RRF: **{config_label(best)}**. It meets the predeclared dense-comparison criteria on this small silver set; validate it on human labels before changing defaults.")
    else:
        metrics = observed["metrics"]
        lines.append(f"Highest-R@5 fusion observed: **{config_label(observed)}** (R@5 {metrics['recall_at_5']:.3f}, MRR@10 {metrics['mrr_at_10']:.3f}). It was rejected because its MRR@10 remains more than 0.02 below dense-only.")
        lines.append("No weighted RRF configuration met the predeclared dense-comparison criteria. Keep **Dense as primary ranking** and use BM25 for complementary recall/fallback rather than as an equal-weight primary fusion input.")
    lines += ["", "## Limitations", "", "- This is a small, automatically silver-labeled sample; differences are not statistically significant.", "- Weights were selected from the same sample, so they must not be treated as final production tuning.", "- Historical ticket evidence remains sparse-only and was not made a positive primary label when official documentation existed."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze existing silver results and sweep non-reranked weighted RRF.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--regressions", type=Path, default=DEFAULT_REGRESSIONS)
    parser.add_argument("--sweep-json", type=Path, default=DEFAULT_SWEEP_JSON)
    parser.add_argument("--sweep-markdown", type=Path, default=DEFAULT_SWEEP_MD)
    args = parser.parse_args()

    cases, report = load_jsonl(args.dataset), json.loads(args.report.read_text(encoding="utf-8"))
    regressions, counts = build_regression_rows(cases, report), complementarity(cases, report)
    args.regressions.parent.mkdir(parents=True, exist_ok=True)
    args.regressions.write_text(markdown_regressions(regressions, counts), encoding="utf-8")

    inputs = candidate_lists(cases)
    rows = make_sweep(cases, inputs)
    best = best_configuration(rows)
    observed = best_observed_configuration(rows)
    payload = {"label_type": "silver_auto", "positive_document_queries": 15, "rows": rows, "best_configuration": best,
               "best_observed_configuration": observed,
               "recommendation": "weighted_rrf_candidate" if best else "dense_primary_bm25_complementary_fallback"}
    args.sweep_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.sweep_markdown.write_text(markdown_sweep(rows, best, observed), encoding="utf-8")
    print(f"Regression analysis: {args.regressions}")
    print(f"Sweep JSON: {args.sweep_json}")
    print(f"Sweep Markdown: {args.sweep_markdown}")
    print(f"Regressions: {len(regressions)}; complementarity: {counts}; best: {config_label(best) if best else 'none'}")


if __name__ == "__main__":
    main()
