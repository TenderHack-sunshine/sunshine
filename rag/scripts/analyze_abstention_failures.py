from __future__ import annotations

"""Write a compact, reproducible analysis of known unsafe abstention cases.

This script is intentionally read-only with respect to runtime RAG behaviour.  It
uses the saved independent evaluation report, whose candidates and scores are the
ones on which the three failures were observed.
"""

import json
from pathlib import Path


DEFAULT_REPORT = Path("data/processed/eval/rag_quality_eval_report.json")
DEFAULT_OUTPUT = Path("data/processed/eval/abstention_false_answer_forensics.md")
CANONICAL = Path("data/processed/index/all_chunks.jsonl")


CAUSES = {
    "где посмотреть темы обращений": {
        "primary": "D. CONFIDENCE_POLICY_FAILURE",
        "explanation": (
            "Dense top score is 0.556 (< 0.60) and retriever agreement is only "
            "0.15, but compacted evidence starts with a raw BM25 candidate scored "
            "8.360. ConfidenceEvaluator uses the first available `raw_score` as "
            "top_score and consequently compares a BM25 score to the dense-score "
            "threshold. The retrieved manuals are related to обращения but do not "
            "establish where a user can browse the taxonomy of topics."
        ),
    },
    "какая комиссия портала за размещение оферты": {
        "primary": "B. PARTIAL_KNOWLEDGE_FAILURE",
        "explanation": (
            "The corpus retrieves material about offers and signing them, but the "
            "top evidence does not state a commission or its amount. Dense score "
            "0.646 and a small top-1/top-2 gap (0.004) describe topical proximity, "
            "not support for the requested fact. Low cross-retriever agreement "
            "(0.15) was available but unused by the default confidence policy."
        ),
    },
    "назови точный штраф за неподписание оферты": {
        "primary": "B. PARTIAL_KNOWLEDGE_FAILURE",
        "explanation": (
            "The corpus has related documents on offers, signing, and an unrelated "
            "contract-penalty field, but no retrieved evidence establishes the "
            "requested exact penalty. Dense score 0.633 and agreement 0.10 again "
            "measure topic similarity rather than claim sufficiency."
        ),
    },
}


def _score(item: dict) -> str:
    raw = item.get("raw_score")
    rrf = item.get("rrf_score")
    return f"raw={raw!r}; rrf={rrf!r}"


def _candidate_lines(name: str, candidates: list[dict]) -> list[str]:
    lines = [f"**{name}**"]
    if not candidates:
        return lines + ["- no candidates recorded"]
    for item in candidates[:5]:
        title = item.get("title") or "(untitled manual chunk)"
        lines.append(
            f"- #{item.get('rank')}: `{item.get('chunk_id')}` — `{item.get('document_id')}`; "
            f"{_score(item)}; title: {title}"
        )
    return lines


def _texts_for(ids: set[str]) -> dict[str, str]:
    texts: dict[str, str] = {}
    with CANONICAL.open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            if row["chunk_id"] in ids:
                texts[row["chunk_id"]] = row["text"]
    return texts


def render(report: dict) -> str:
    rows = {row["query"]: row for row in report["diagnostics"]}
    answer_ids = {rows[query]["hybrid"][0]["chunk_id"] for query in CAUSES}
    answer_texts = _texts_for(answer_ids)
    output = [
        "# Abstention false-answer forensics",
        "",
        "Source: `data/processed/eval/rag_quality_eval_report.json` (independent derived-SILVER baseline). "
        "This report is analysis-only; no RAG policy was changed before it was produced.",
        "",
        "The generator is extractive: it returns the first compacted evidence chunk. Therefore these are not "
        "generation-overreach failures. The existing groundedness check only establishes that an official source "
        "was present; it does not establish that the source supports the particular requested claim.",
    ]
    for query, diagnosis in CAUSES.items():
        row = rows[query]
        confidence = row["confidence"]
        grounded = row["groundedness"]
        answer_id = row["hybrid"][0]["chunk_id"]
        answer = answer_texts.get(answer_id, "(canonical chunk is unavailable)")
        output.extend([
            "",
            f"## {query}",
            "",
            "- Expected label: `INSUFFICIENT_KNOWLEDGE` / `PARTIAL_KNOWLEDGE` (expected escalation).",
            f"- Actual RAG status: `{row['actual_decision']}`.",
            f"- Generated answer: extractive return of `{answer_id}` (not a free-form LLM claim): "
            f"> {answer[:700].replace(chr(10), ' ')}",
            f"- Grounding result: answer_produced={grounded['answer_produced']}; "
            f"official_evidence_present={grounded['official_evidence_present']}; "
            f"answer_without_evidence={grounded['flag_answer_without_evidence']}; "
            "claim-level support was not checked.",
            f"- Current confidence: top_score={confidence['top_score']:.6f}; "
            f"top1/top2 gap={confidence['top1_top2_gap']:.6f}; "
            f"official candidates={confidence['num_official_candidates']}; "
            f"retriever agreement={confidence['retrieval_agreement']:.2f}.",
            "- Current abstention decision: `ANSWER`; no abstention reason was emitted.",
            f"- Primary cause: **{diagnosis['primary']}**.",
            f"- Why it answered incorrectly: {diagnosis['explanation']}",
            "",
            "### Recorded retrieved chunks",
            "",
        ])
        for label, key in (("Official BM25", "bm25"), ("Official dense", "dense"), ("Pipeline candidate order", "hybrid")):
            output.extend(_candidate_lines(label, row.get(key, [])))
            output.append("")
    output.extend([
        "## Cross-case conclusion",
        "",
        "- No case is primarily a retrieval failure: all retrieved documents are topically related, but they do not "
        "support the requested precise fact or action.",
        "- No case is generation overreach: the current generator is extractive.",
        "- The policy has two distinct defects to evaluate on a separately human-labelled DEV set: score-scale mixing "
        "when a BM25 result becomes the first compacted candidate, and lack of claim/evidence sufficiency for "
        "partial-knowledge questions.",
        "- Existing grounding is evidence-presence validation, not claim-level grounding. It did not flag these answers "
        "because an official evidence chunk existed.",
    ])
    return "\n".join(output) + "\n"


def main() -> None:
    report = json.loads(DEFAULT_REPORT.read_text(encoding="utf-8"))
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(render(report), encoding="utf-8")
    print(DEFAULT_OUTPUT)


if __name__ == "__main__":
    main()
