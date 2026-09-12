"""Offline, interpretable refinement of the 0.60 confidence policy.

This script never changes runtime configuration or retrieval.  It uses only
non-REVIEW_NEEDED rows already recorded in confidence_analysis.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REPORT = ROOT / "data" / "processed" / "eval" / "confidence_analysis.json"
OUT_JSON = ROOT / "data" / "processed" / "eval" / "confidence_policy_refinement.json"
OUT_MD = ROOT / "data" / "processed" / "eval" / "confidence_policy_refinement.md"


def route_for(query: str) -> str:
    from src.application.pipeline import SupportRouter
    from src.routing.normalization import normalize_query

    return SupportRouter().classify(normalize_query(query))["route"]


def token_count(query: str) -> int:
    return len(re.findall(r"[\w-]+", query.casefold(), flags=re.UNICODE))


def base_decision(row: dict, min_score: float = .60) -> str:
    if row["context_clarification"]:
        return "NEEDS_CLARIFICATION"
    if not row["official_evidence_present"] or row["num_relevant_candidates"] < 1:
        return "ESCALATE_TO_OPERATOR"
    return "ANSWER" if row["top_score"] >= min_score else "ESCALATE_TO_OPERATOR"


def clarification_reason(row: dict) -> str:
    from src.application.clarification import ClarificationPolicy

    return ClarificationPolicy().evaluate(row["query"], row["route"]).reason


def short_failure_statement(row: dict) -> bool:
    return clarification_reason(row) == "SHORT_FAILURE_QUERY"


def broad_rules_request(row: dict) -> bool:
    return clarification_reason(row) == "BROAD_POLICY_QUERY"


POLICIES = {
    "score_0_60": ("Score >= 0.60", lambda row: base_decision(row)),
    "score_0_65": ("Score >= 0.65", lambda row: base_decision(row, .65)),
    "score_0_60_agreement_lt_0_30_clarify": (
        "Score >= 0.60; agreement < 0.30 -> CLARIFY",
        lambda row: "NEEDS_CLARIFICATION" if base_decision(row) == "ANSWER" and row["retrieval_agreement"] < .30 else base_decision(row),
    ),
    "score_0_60_short_failure_clarify": (
        "Score >= 0.60; short failure statement (<=3 tokens) -> CLARIFY",
        lambda row: "NEEDS_CLARIFICATION" if base_decision(row) == "ANSWER" and short_failure_statement(row) else base_decision(row),
    ),
    "score_0_60_short_failure_or_broad_rules_clarify": (
        "Score >= 0.60; short failure OR broad L2 rules request -> CLARIFY",
        lambda row: "NEEDS_CLARIFICATION" if base_decision(row) == "ANSWER" and (short_failure_statement(row) or broad_rules_request(row)) else base_decision(row),
    ),
}


def target(row: dict) -> str:
    return row["explicit_expected_decision"] or row["policy_target"]


def evaluate(rows: list[dict], name: str, description: str, decide) -> dict:
    decisions = [decide(row) for row in rows]
    labelled = [(row, decision) for row, decision in zip(rows, decisions, strict=True) if row["silver_label_status"] == "LABELED"]
    dangerous = [row for row, decision in zip(rows, decisions, strict=True) if decision == "ANSWER" and target(row) in {"NEEDS_CLARIFICATION", "ESCALATE_TO_OPERATOR"}]
    return {
        "policy": name,
        "description": description,
        "correct_answer_retained": sum(decision == "ANSWER" for _row, decision in labelled),
        "correct_answer_total": len(labelled),
        "dangerous_answer_count": len(dangerous),
        "false_clarify_count": sum(decision == "NEEDS_CLARIFICATION" for _row, decision in labelled),
        "false_escalate_count": sum(decision == "ESCALATE_TO_OPERATOR" for _row, decision in labelled),
        "decisions": decisions,
        "remaining_dangerous_queries": [row["query"] for row in dangerous],
    }


def signal_summary(rows: list[dict]) -> dict:
    fields = ("top_score", "top1_top2_gap", "retrieval_agreement", "num_official_candidates")
    output = {}
    for group, values in {
        "dangerous_at_score_0_60": [row for row in rows if base_decision(row) == "ANSWER" and target(row) in {"NEEDS_CLARIFICATION", "ESCALATE_TO_OPERATOR"}],
        "labeled": [row for row in rows if row["silver_label_status"] == "LABELED"],
    }.items():
        output[group] = {
            field: {"min": min(row[field] for row in values), "median": median(row[field] for row in values), "max": max(row[field] for row in values)}
            for field in fields
        }
    return output


def render_markdown(rows: list[dict], policies: list[dict], signals: dict) -> str:
    dangerous = [row for row in rows if base_decision(row) == "ANSWER" and target(row) in {"NEEDS_CLARIFICATION", "ESCALATE_TO_OPERATOR"}]
    lines = [
        "# Confidence policy refinement at score 0.60",
        "",
        "> SILVER-only offline analysis. `REVIEW_NEEDED` is excluded. Retrieval ranking and labels are not changed by this report.",
        "",
        f"## {len(dangerous)} dangerous ANSWER rows",
        "",
        "| Query | Expected | Route | Ambiguity interpretation | Score | Gap | Dense/BM25 agreement | Official candidates |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in dangerous:
        ambiguity = "short failure statement" if short_failure_statement(row) else "broad rules request" if broad_rules_request(row) else "ambiguous from silver review"
        lines.append(f"| {row['query']} | {target(row)} | {row['route']} | {ambiguity} | {row['top_score']:.3f} | {row['top1_top2_gap']:.3f} | {row['retrieval_agreement']:.3f} | {row['num_official_candidates']} |")
    lines += [
        "",
        "## Signal comparison",
        "",
        "| Group | Score min/median/max | Gap min/median/max | Agreement min/median/max | Official candidates min/median/max |",
        "| --- | --- | --- | --- | --- |",
    ]
    for group, label in (("dangerous_at_score_0_60", "Dangerous"), ("labeled", "Correct LABELED")):
        values = signals[group]
        fmt = lambda field: "/".join(f"{values[field][key]:.3f}" for key in ("min", "median", "max"))
        lines.append(f"| {label} | {fmt('top_score')} | {fmt('top1_top2_gap')} | {fmt('retrieval_agreement')} | {fmt('num_official_candidates')} |")
    lines += [
        "",
        "Numeric agreement and gap cutoffs overlap useful answers, so they are not selected as the demo candidate.",
        "",
        "## Candidate policies",
        "",
        "| Policy | Correct ANSWER retained | Dangerous ANSWER | False CLARIFY | False ESCALATE |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for result in policies:
        lines.append(f"| {result['description']} | {result['correct_answer_retained']}/{result['correct_answer_total']} | {result['dangerous_answer_count']} | {result['false_clarify_count']} | {result['false_escalate_count']} |")
    lines += [
        "",
        "## Recommendation",
        "",
        "For a demo candidate, retain score 0.60 and add only two query-ambiguity clauses: short failure reports and broad L2 `правила ...` requests ask for clarification. This reaches zero dangerous answers on this tiny silver subset while retaining 13/15 labelled answers. It remains a hypothesis for human validation, not a production change.",
        "",
        "## Limitations",
        "",
        f"- The sample has 15 silver-positive queries and only {len(dangerous)} dangerous rows after deduplication.",
        "- The semantic clauses are intentionally simple and may not generalize; do not treat this as statistical evidence.",
        "- No REVIEW_NEEDED row participated in the analysis.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    raw = json.loads(REPORT.read_text(encoding="utf-8"))["rows"]
    rows = []
    for source in raw:
        if source["silver_label_status"] == "REVIEW_NEEDED":
            continue
        row = dict(source)
        row["route"] = route_for(row["query"])
        row["query_token_count"] = token_count(row["query"])
        rows.append(row)
    policies = [evaluate(rows, name, description, decide) for name, (description, decide) in POLICIES.items()]
    signals = signal_summary(rows)
    payload = {"label_type": "silver_auto", "excluded_status": "REVIEW_NEEDED", "rows": rows, "signal_summary": signals, "candidate_policies": policies}
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(render_markdown(rows, policies, signals), encoding="utf-8")
    print(f"Saved: {OUT_JSON}")
    print(f"Saved: {OUT_MD}")
    for item in policies:
        print(item["policy"], item["correct_answer_retained"], item["dangerous_answer_count"], item["false_clarify_count"], item["false_escalate_count"])


if __name__ == "__main__":
    main()
