from __future__ import annotations

"""Write a truthful checkpoint report before human calibration begins."""

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/processed/eval/rag_certification_report.md"


def rows(name: str) -> list[dict]:
    path = ROOT / f"data/eval/abstention_calibration_{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def summary(name: str) -> str:
    values = rows(name)
    proposals = Counter(item["proposed_label"] for item in values)
    pending = sum(item["review_status"] == "PENDING_HUMAN_REVIEW" for item in values)
    return (
        f"- {name}: {len(values)} cases — {proposals['ANSWERABLE']} proposed answerable, "
        f"{proposals['INSUFFICIENT_KNOWLEDGE']} proposed insufficient-knowledge, "
        f"{proposals['AMBIGUOUS_QUERY']} proposed ambiguous; {pending} pending human review."
    )


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join([
        "# RAG certification checkpoint",
        "",
        "## Status: REVIEW — not eligible for PASS",
        "",
        "The requested DEV and FINAL sets are structured review queues, not human gold labels. No threshold, prompt, or "
        "production abstention policy has been calibrated on them. This report deliberately does not convert proposed labels "
        "into evaluation results.",
        "",
        "## Retrieval quality",
        "",
        "- Baseline derived-SILVER Hybrid: R@1 0.472, R@3 0.722, R@5 0.778, R@10 0.861, MRR@10 0.608.",
        "- Baseline derived-SILVER typo Hybrid R@10: 1.000.",
        "- No retrieval implementation or retrieval parameters were changed in this safety checkpoint.",
        "",
        "## Answer quality and abstention safety",
        "",
        "- Before the score-scale correction (derived-SILVER): 28 / 36 answerable accepted; 7 / 11 expected escalations "
        "safely rejected; 3 / 11 dangerous false answers.",
        "- After the correction (derived-SILVER, not human gold): 29 / 36 answerable accepted; 8 / 11 expected escalations "
        "safely rejected; 3 / 11 dangerous false answers. The remaining three are partial-knowledge cases and require DEV "
        "review before enabling the guard globally.",
        "- Forensic result: one confidence score-scale defect and two partial-knowledge failures; none is primarily a retrieval "
        "or free-form-generation failure.",
        "- The score-scale defect is corrected: `CONFIDENCE_MIN_OFFICIAL_SCORE` now receives only an official dense cosine "
        "score, never a raw BM25 score. This is a semantic correctness fix, not a threshold change.",
        "- The claim/evidence guard is opt-in pending DEV review: `EVIDENCE_SUFFICIENCY_ENABLED=0` by default.",
        "",
        "## Current decision logic",
        "",
        "1. Deterministic local profanity hard gate; then deterministic clarification; then routing and retrieval.",
        "2. Empty evidence escalates. For official dense evidence, the configured cosine threshold is applied only to the dense "
        "score. Optional retrieval-agreement policy remains disabled by default.",
        "3. With `EVIDENCE_SUFFICIENCY_ENABLED=1`, an answer is escalated where returned extractive evidence lacks an explicit "
        "navigation path for a navigation request, or lacks the named fact requested by a specific-fact question.",
        "4. Every safe post-retrieval escalation still emits `diagnostics.knowledge_gap` as `NO_RELEVANT_DOCUMENTS` or "
        "`PARTIAL_KNOWLEDGE`; clarification keeps `AMBIGUOUS_QUERY`.",
        "",
        "## Calibration data",
        "",
        summary("dev"), summary("final"),
        "- DEV and FINAL have disjoint query texts. Answerable proposals cite exact document/chunk IDs, a minimal evidence span, "
        "and expected facts. Unanswerable proposals state a gap type and rationale.",
        "- Required next action: a human reviewer sets `label`, confirms/edits evidence and rationale, and changes "
        "`review_status` to `HUMAN_REVIEWED` using `scripts/review_abstention_dev.py`. FINAL must remain untouched during DEV tuning.",
        "",
        "## Grounding and knowledge gap",
        "",
        "- The generator remains extractive. Existing grounding establishes evidence presence, not claim-level support; the opt-in "
        "guard supplies a narrow deterministic claim/evidence check for the discovered patterns.",
        "- Profanity is now a deterministic local hard gate; the former Rubert classifier/threshold are no longer a runtime dependency.",
        "",
        "## Tests and latency",
        "",
        "- Full suite: 136 passed.",
        "- Deterministic profanity benchmark: 156 cases; TP=101, FP=0, TN=55, FN=0; precision=1.000, recall=1.000, F1=1.000; "
        "mean=0.011 ms, p50=0.008 ms, p95=0.023 ms on this CPU run.",
        "- Evaluation worker root cause: each dense timeout previously left a non-cancellable ThreadPoolExecutor request alive. "
        "The retriever now permits one daemon request at a time; a timed-out/in-flight request becomes a controlled dense failure "
        "and BM25 fallback. The 50-case retrieval evaluation now completes and preserves the baseline retrieval metrics.",
        "",
        "## Certification rule",
        "",
        "PASS requires 0 dangerous false answers and no grounding violations on a human-labelled FINAL set, with acceptable "
        "answerable coverage. Until then this is REVIEW, not PASS.",
        "",
    ]), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
