"""Evaluate dense-primary evidence decisions on the SILVER retrieval dataset.

No model is trained and no production threshold is changed. Each query obtains
one live candidate trace; all confidence-threshold candidates are then evaluated
locally over the same feature rows.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.application.evidence import compact_evidence
from src.application.factory import build_rag_service
from src.core.config import Settings
from src.retrieval.mvp import rrf_fuse


DATASET = ROOT / "data" / "eval" / "retrieval_eval_silver.jsonl"
OUT_JSON = ROOT / "data" / "processed" / "eval" / "confidence_analysis.json"
OUT_MD = ROOT / "data" / "processed" / "eval" / "confidence_analysis.md"
DECISION_ALIASES = {"CLARIFY": "NEEDS_CLARIFICATION", "ESCALATE": "ESCALATE_TO_OPERATOR"}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalized_decision(value: str | None) -> str | None:
    return DECISION_ALIASES.get(value or "", value)


def semantic_decision(status: str) -> str | None:
    return {"LABELED": "ANSWER", "AMBIGUOUS": "NEEDS_CLARIFICATION", "NO_RELEVANT_EVIDENCE": "ESCALATE_TO_OPERATOR"}.get(status)


def document_rank(results: list[dict], documents: list[str]) -> int | None:
    return next((rank for rank, item in enumerate(results, 1) if item.get("document_id") in documents), None)


def document_metrics(rows: list[tuple[dict, list[dict]]]) -> dict[str, float | int | None]:
    labelled = [(case, values) for case, values in rows if case.get("relevant_document_ids")]
    ranks = [document_rank(values, case["relevant_document_ids"]) for case, values in labelled]
    output: dict[str, float | int | None] = {"labelled_queries": len(labelled)}
    for k in (5, 10):
        output[f"recall_at_{k}"] = sum(rank is not None and rank <= k for rank in ranks) / len(ranks) if ranks else None
    output["mrr_at_10"] = sum(1 / rank if rank is not None and rank <= 10 else 0.0 for rank in ranks) / len(ranks) if ranks else None
    return output


def policy_decision(row: dict, min_score: float, min_agreement: float, min_sources: int) -> str:
    if row["context_clarification"]:
        return "NEEDS_CLARIFICATION"
    if row["num_relevant_candidates"] < min_sources or not row["official_evidence_present"]:
        return "ESCALATE_TO_OPERATOR"
    if row["top_score"] < min_score:
        return "ESCALATE_TO_OPERATOR"
    if min_agreement > 0 and row["retrieval_agreement"] < min_agreement:
        return "NEEDS_CLARIFICATION"
    return "ANSWER"


def score_config(rows: list[dict], min_score: float, min_agreement: float, min_sources: int) -> dict[str, Any]:
    decisions = [policy_decision(row, min_score, min_agreement, min_sources) for row in rows]
    target_rows = [row for row in rows if row["policy_target"]]
    targets = [row["explicit_expected_decision"] or row["policy_target"] for row in target_rows]
    dangerous = sum(decision == "ANSWER" and row["policy_target"] in {"NEEDS_CLARIFICATION", "ESCALATE_TO_OPERATOR"} for row, decision in zip(rows, decisions, strict=True))
    expected_dangerous = sum(decision == "ANSWER" and row["explicit_expected_decision"] in {"NEEDS_CLARIFICATION", "ESCALATE_TO_OPERATOR"} for row, decision in zip(rows, decisions, strict=True))
    correct = sum(decision == target for decision, target in zip((policy_decision(row, min_score, min_agreement, min_sources) for row in target_rows), targets, strict=True))
    labeled_answer = sum(decision == "ANSWER" for row, decision in zip(rows, decisions, strict=True) if row["silver_label_status"] == "LABELED")
    return {"confidence_min_official_score": min_score, "confidence_min_agreement": min_agreement, "confidence_min_sources": min_sources,
            "dangerous_silver_answers": dangerous, "dangerous_explicit_answers": expected_dangerous,
            "policy_correct": correct, "policy_total": len(target_rows), "labeled_answers": labeled_answer,
            "decisions": {name: decisions.count(name) for name in ("ANSWER", "NEEDS_CLARIFICATION", "ESCALATE_TO_OPERATOR")}}


def collect(cases: list[dict]) -> tuple[list[dict], dict[str, dict[str, float | int | None]]]:
    # Offline retrieval analysis intentionally uses the explicit lightweight
    # safety backend when local fine-tuned artifacts are not mounted.
    settings = Settings(retrieval_strategy="dense_primary", rerank_enabled=False, profanity_backend="rule")
    service = build_rag_service(settings)
    rows, dense_primary, hybrid, bm25 = [], [], [], []
    for index, case in enumerate(cases, 1):
        query = case["query"]
        normalized = service.preprocessor.process(query)["normalized_query"]
        context_clarification = bool(normalized and service.context.needs_clarification(normalized))
        route = service.router.classify(normalized or query)
        trace = service.retriever.retrieve_with_trace(normalized or query, technical=route["technical"], top_k=20)
        candidates = compact_evidence(trace["results"][:service.final_top_k], max_per_document=service.evidence_max_per_document)
        features = service.confidence.features(candidates, trace)
        actual = "NEEDS_CLARIFICATION" if context_clarification else service.confidence.decide(route["route"], candidates, features)[0]
        explicit = normalized_decision(case.get("expected_decision"))
        target = semantic_decision(case.get("silver_label_status", ""))
        dense_results = trace["official_dense"]
        sparse_lists = [trace["official_bm25"]]
        if trace["ticket_bm25"]:
            sparse_lists.append(trace["ticket_bm25"])
        bm25_results = rrf_fuse(sparse_lists, k=service.retriever.rrf_k)
        hybrid_lists = [trace["official_bm25"], dense_results]
        hybrid_weights = [1.0, 1.0]
        if trace["ticket_bm25"]:
            hybrid_lists.append(trace["ticket_bm25"])
            hybrid_weights.append(1.0)
        hybrid_results = rrf_fuse(hybrid_lists, k=service.retriever.rrf_k, weights=hybrid_weights) if dense_results else bm25_results
        rows.append({
            "query": query, "silver_label_status": case.get("silver_label_status"), "policy_target": target,
            "explicit_expected_decision": explicit, "expected_decision_conflicts_silver": bool(target and explicit and target != explicit),
            "actual_decision": actual, "context_clarification": context_clarification,
            "top_score": features["top_score"], "top1_top2_gap": features["top1_top2_gap"],
            "retrieval_agreement": features["retrieval_agreement"], "num_official_candidates": features["num_official_candidates"],
            "num_relevant_candidates": features["num_relevant_candidates"], "official_evidence_present": features["official_evidence_present"],
            "dense_rank_of_relevant": document_rank(dense_results, case.get("relevant_document_ids", [])),
            "bm25_rank_of_relevant": document_rank(bm25_results, case.get("relevant_document_ids", [])),
            "retrieval_strategy": trace["retrieval_strategy"], "dense_primary_used": trace["dense_primary_used"],
            "bm25_rescue_used": trace["bm25_rescue_used"], "bm25_fallback_used": trace["bm25_fallback_used"],
            "dense_available": trace["dense_available"], "dense_candidates": trace["dense_candidates"],
            "bm25_candidates": trace["bm25_candidates"], "final_candidates": trace["final_candidates"],
        })
        dense_primary.append((case, trace["fused"]))
        hybrid.append((case, hybrid_results))
        bm25.append((case, bm25_results))
        print(f"[{index}/{len(cases)}] assessed")
    return rows, {"DENSE_PRIMARY": document_metrics(dense_primary), "HYBRID_RRF": document_metrics(hybrid), "BM25": document_metrics(bm25)}


def render_markdown(rows: list[dict], retrieval: dict[str, dict], candidates: list[dict]) -> str:
    conflicts = [row for row in rows if row["expected_decision_conflicts_silver"]]
    dangerous = [row for row in rows if row["actual_decision"] == "ANSWER" and row["policy_target"] in {"NEEDS_CLARIFICATION", "ESCALATE_TO_OPERATOR"}]
    lines = [
        "# Dense-primary confidence analysis",
        "",
        "> **SILVER / AUTO-LABELED analysis.** `REVIEW_NEEDED` rows are excluded from threshold selection. Reranking is disabled.",
        "",
        "## Document retrieval comparison",
        "",
        "| Strategy | R@5 | R@10 | MRR@10 | Labels |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, values in retrieval.items():
        lines.append(f"| {name} | {values['recall_at_5']:.3f} | {values['recall_at_10']:.3f} | {values['mrr_at_10']:.3f} | {values['labelled_queries']} |")
    lines += ["", "## Current dense-primary decision policy", "", f"- Dangerous silver status → ANSWER: **{len(dangerous)}**", f"- Explicit expected-decision conflicts with silver semantics: **{len(conflicts)}**", ""]
    if dangerous:
        lines.append("### Dangerous answers")
        lines.extend(f"- **{row['query']}**: {row['silver_label_status']} → `{row['actual_decision']}`" for row in dangerous)
        lines.append("")
    if conflicts:
        lines.append("### Explicit expectation conflicts")
        lines.extend(f"- **{row['query']}**: silver `{row['policy_target']}` vs explicit `{row['explicit_expected_decision']}`" for row in conflicts)
        lines.append("")
    lines += ["## Candidate confidence configurations", "", "| Min official score | Min agreement | Min sources | Dangerous silver ANSWER | Policy correct | Labeled ANSWER |", "| ---: | ---: | ---: | ---: | ---: | ---: |"]
    for candidate in candidates[:12]:
        lines.append(f"| {candidate['confidence_min_official_score']:.2f} | {candidate['confidence_min_agreement']:.2f} | {candidate['confidence_min_sources']} | {candidate['dangerous_silver_answers']} | {candidate['policy_correct']}/{candidate['policy_total']} | {candidate['labeled_answers']} |")
    lines += ["", "## Per-query signals", "", "The JSON artifact contains all requested per-query fields: scores, score gap, agreement, evidence counts, dense/BM25 relevant ranks, expected/actual decision, and silver status.", "", "## Limitations", "", "- Only 15 positive document labels exist and all labels are silver, not gold.", "- Threshold candidates are descriptive and must be human-validated before production changes.", "- No query-specific routing or score rules were introduced."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze dense-primary confidence and sparse rescue on the silver dataset.")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path, default=OUT_JSON)
    parser.add_argument("--markdown", type=Path, default=OUT_MD)
    args = parser.parse_args()
    cases = load_jsonl(args.dataset)
    rows, retrieval = collect(cases)
    candidates = [score_config(rows, score, agreement, sources) for score in (0.0, .55, .60, .65) for agreement in (0.0, .05, .10) for sources in (1, 2)]
    candidates.sort(key=lambda item: (item["dangerous_silver_answers"], -item["policy_correct"], -item["labeled_answers"], item["confidence_min_official_score"], item["confidence_min_agreement"], item["confidence_min_sources"]))
    payload = {"label_type": "silver_auto", "rows": rows, "retrieval_comparison": retrieval, "threshold_candidates": candidates,
               "dangerous_counts": {"silver_ambiguous_or_missing_to_answer": sum(row["actual_decision"] == "ANSWER" and row["policy_target"] in {"NEEDS_CLARIFICATION", "ESCALATE_TO_OPERATOR"} for row in rows),
                                    "explicit_clarify_or_escalate_to_answer": sum(row["actual_decision"] == "ANSWER" and row["explicit_expected_decision"] in {"NEEDS_CLARIFICATION", "ESCALATE_TO_OPERATOR"} for row in rows)}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.markdown.write_text(render_markdown(rows, retrieval, candidates), encoding="utf-8")
    print(f"Saved: {args.output}")
    print(f"Saved: {args.markdown}")
    print(json.dumps(payload["retrieval_comparison"], ensure_ascii=False))
    print(payload["dangerous_counts"])


if __name__ == "__main__":
    main()
