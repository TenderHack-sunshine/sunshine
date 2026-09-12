"""Build review-ready, deterministic demo artifacts from an E2E report.

This script never invokes retrieval or generation.  It only joins the saved E2E
result with the canonical corpus so a reviewer can inspect all evidence without
having to locate JSONL chunks manually.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.config import Settings


DEFAULT_E2E = ROOT / "data" / "processed" / "eval" / "e2e_demo_report.json"
DEFAULT_CHUNKS = ROOT / "data" / "processed" / "index" / "all_chunks.jsonl"
DEFAULT_RETRIEVAL = ROOT / "data" / "processed" / "eval" / "retrieval_eval_silver_report.json"
OUT_DIR = ROOT / "data" / "processed" / "eval"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_chunks(path: Path) -> dict[str, dict[str, Any]]:
    chunks: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                item = json.loads(line)
                chunks[str(item["chunk_id"])] = item
    return chunks


def compact(text: object, limit: int = 700) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def normalized(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "").casefold()).strip()


def answer_flags(row: dict[str, Any], chunks: dict[str, dict[str, Any]]) -> list[str]:
    """Conservative deterministic flags; they are review prompts, not a judge."""
    flags = list(row.get("grounding_warnings", []))
    evidence = row.get("evidence", [])
    official = [item for item in evidence if item.get("authority") == "official"]
    tickets = [item for item in evidence if item.get("authority") == "case_history"]
    if not evidence:
        flags.append("ANSWER_ZERO_EVIDENCE")
    if not official:
        flags.append("ANSWER_ZERO_OFFICIAL_EVIDENCE")
    if tickets and not official:
        flags.append("ANSWER_ONLY_SUPPORT_TICKETS")
    if official and tickets and next(i for i, item in enumerate(evidence) if item.get("authority") == "case_history") < next(i for i, item in enumerate(evidence) if item.get("authority") == "official"):
        flags.append("TICKET_PRECEDES_OFFICIAL_EVIDENCE")
    expected = row.get("expected", {}).get("expected_decision")
    if expected in {"NEEDS_CLARIFICATION", "ESCALATE_TO_OPERATOR"}:
        flags.append("ANSWER_AFTER_EXPECTED_NON_ANSWER")
    answer = normalized(row.get("answer"))
    texts = [normalized(chunks.get(str(item.get("chunk_id")), {}).get("text")) for item in evidence]
    # The current generator is extractive.  A non-substring is therefore an
    # objective signal to inspect, while avoiding any speculative LLM judging.
    if answer and texts and not any(answer in text for text in texts):
        flags.append("ANSWER_NOT_EXTRACTIVE_SUBSTRING_OF_EVIDENCE")
    return sorted(set(flags))


def source_block(source: dict[str, Any], chunks: dict[str, dict[str, Any]]) -> list[str]:
    chunk = chunks.get(str(source.get("chunk_id")), {})
    title = source.get("title") or chunk.get("title") or "—"
    section = source.get("section") or chunk.get("section") or "—"
    lines = [
        f"- **Title:** {title}",
        f"  - **Section:** {section}",
        f"  - **document_id:** `{source.get('document_id')}`",
        f"  - **chunk_id:** `{source.get('chunk_id')}`",
        f"  - **Excerpt:** {compact(chunk.get('text')) if chunk else '_Chunk not found in canonical corpus._'}",
    ]
    return lines


def grounding_review(e2e: dict[str, Any], chunks: dict[str, dict[str, Any]]) -> tuple[str, Counter[str]]:
    runtime = e2e.get("runtime", {})
    lines = [
        "# Final grounding review", "",
        "This is a deterministic review packet, not an automatic factual certification.",
        f"Source E2E runtime: `{runtime.get('profanity_backend')}`; profanity mode: `{runtime.get('ml_profanity_e2e')}`.",
        "This packet remains a human grounding-review aid, not an automatic certification.", "",
    ]
    all_flags: Counter[str] = Counter()
    rows = [row for row in e2e.get("scenarios", []) if row.get("decision") == "ANSWER"]
    for row in rows:
        flags = answer_flags(row, chunks)
        all_flags.update(flags)
        official = [source for source in row.get("evidence", []) if source.get("authority") == "official"]
        secondary = [source for source in row.get("evidence", []) if source.get("authority") != "official"]
        lines += [
            f"## {row['id']}", "",
            f"**Query:** {row['query']}", "",
            f"**Route:** `{row.get('route')}`", "",
            "**Final answer:**", "", row.get("answer") or "—", "",
            "### Official evidence", "",
        ]
        if official:
            for source in official:
                lines.extend(source_block(source, chunks))
        else:
            lines.append("- _No official evidence returned._")
        lines += ["", "### Secondary evidence", ""]
        if secondary:
            for source in secondary:
                lines.extend(source_block(source, chunks))
        else:
            lines.append("- _None._")
        lines += ["", "### Grounding check", "", "- [ ] Answer is supported by the evidence", "- [ ] No unsupported factual claims", "- [ ] No contradiction with an official source", "- [ ] Official source has priority"]
        lines += ["", f"**Deterministic flags:** {', '.join(flags) if flags else 'none'}", ""]
    return "\n".join(lines) + "\n", all_flags


def demo_queries(e2e: dict[str, Any]) -> str:
    selected = [
        ("l1_mchd", "Normal L1 official answer"),
        ("l1_paraphrase", "Paraphrase handling"),
        ("l2_offer_process", "L2 process/policy routing"),
        ("l3_quotation", "L3 technical routing"),
        ("l2_broad_policy", "Clarification before retrieval"),
        ("profanity", "deterministic hard rejection before every downstream stage"),
        ("bm25_rescue", "Dense-primary with sparse BM25 rescue"),
    ]
    by_id = {row["id"]: row for row in e2e.get("scenarios", [])}
    lines = ["# Final live-demo queries", "", "Use only after a green local preflight and E2E run. These cases were structurally verified in the saved E2E dataset; ANSWER grounding remains subject to the review packet.", "", "| Query | Expected route | Expected decision | Demonstrates |", "| --- | --- | --- | --- |"]
    for scenario_id, purpose in selected:
        row = by_id[scenario_id]
        lines.append(f"| {row['query']} | `{row.get('route') or '—'}` | `{row.get('decision')}` | {purpose} |")
    return "\n".join(lines) + "\n"


def system_report(e2e: dict[str, Any], retrieval: dict[str, Any], flags: Counter[str], settings: Settings, pytest_result: str) -> str:
    summary, runtime, latency = e2e.get("summary", {}), e2e.get("runtime", {}), e2e.get("latency", {})
    dense = retrieval.get("metrics", {}).get("DENSE", {}).get("document", {})
    def metric(name: str) -> str:
        item = latency.get(name, {})
        return f"p50={item.get('p50')} ms; p95={item.get('p95')} ms (n={item.get('count')})"
    return f"""# Tender Hack RAG: final system report

## Freeze status

Architecture is frozen. No retrieval ranking, confidence threshold, reranker, ingestion, or model changes were made by this packaging pass.

## Architecture

```text
User query
    ↓
Deterministic local profanity hard gate
    ↓
clarification policy
    ↓
L1/L2/L3 routing
    ↓
Dense-primary retrieval
    ├── BM25 rescue
    └── BM25 fallback
    ↓
evidence preparation (official > taxonomy > historical tickets)
    ↓
confidence decision
    ↓
ANSWER / CLARIFY / ESCALATE
    ↓
grounded extractive generation
```

## Final configuration

```text
RETRIEVAL_STRATEGY={settings.retrieval_strategy}
RERANKER_ENABLED={int(settings.rerank_enabled)}
CONFIDENCE_MIN_OFFICIAL_SCORE={settings.confidence_min_official_score:.2f}
CLARIFICATION_POLICY_ENABLED={int(settings.clarification_policy_enabled)}
PROFANITY_BACKEND={settings.profanity_backend}
```

## Data and index state

- Official Qdrant collection expected: `zakupki_official`, 1,073 points.
- Ticket BM25 artifact: `{settings.data_dir / 'indexes' / 'support_tickets_bm25.pkl'}`.
- Persistent embedding worker and Qdrant were healthy in the latest rehearsal preflight.
- No profanity model weights or threshold file are required.
- Saved E2E runtime backend: `{runtime.get('profanity_backend')}`; mode state: `{runtime.get('ml_profanity_e2e')}`.

## Offline retrieval evaluation

Document-level Dense metrics: Recall@5 = **{dense.get('recall_at_5')}**, Recall@10 = **{dense.get('recall_at_10')}**, MRR@10 = **{dense.get('mrr_at_10')}**.

These are SILVER/AUTO relevance labels, not human gold ground truth.

## E2E result

- Scenarios: **{summary.get('total')}**; PASS: **{summary.get('passed')}**; FAIL: **{summary.get('failed')}**; REVIEW: **{summary.get('review')}**.
- Grounding warnings from runner: **{summary.get('grounding_warnings')}**.
- Deterministic suspicious-answer flags in the review packet: **{sum(flags.values())}** ({', '.join(f'{key}={value}' for key, value in sorted(flags.items())) or 'none'}).

## Tests

Latest full suite: **{pytest_result}**.

## Latency (saved E2E ANSWER scenarios)

- Profanity: {metric('profanity_latency_ms')}
- Dense query embedding: {metric('query_embedding_ms')}
- Qdrant dense search: {metric('dense_search_ms')}
- BM25: {metric('bm25_ms')}
- Generation: {metric('generation_ms')}
- Total: {metric('total_ms')}

## Known limitations / release gate

- The deterministic profanity detector intentionally recognises only high-confidence Russian obscene vocabulary and reasonable obfuscations; it is not a universal toxicity classifier.
- Silver evaluation has a small sample and is not production-scale real-user validation.
- Intel CPU query embeddings dominate latency.
- Reranker is deliberately disabled.
- Confidence and clarification policies are demo baselines and require more data before production generalization.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build final demo review and system-report artifacts.")
    parser.add_argument("--e2e-report", type=Path, default=DEFAULT_E2E)
    parser.add_argument("--canonical-chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--retrieval-report", type=Path, default=DEFAULT_RETRIEVAL)
    parser.add_argument("--pytest-result", default="not recorded by this report build")
    args = parser.parse_args()
    e2e, chunks, retrieval, settings = load_json(args.e2e_report), load_chunks(args.canonical_chunks), load_json(args.retrieval_report), Settings()
    review, flags = grounding_review(e2e, chunks)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = {
        "grounding": OUT_DIR / "final_grounding_review.md",
        "queries": OUT_DIR / "final_demo_queries.md",
        "system": OUT_DIR / "final_system_report.md",
    }
    paths["grounding"].write_text(review, encoding="utf-8")
    paths["queries"].write_text(demo_queries(e2e), encoding="utf-8")
    paths["system"].write_text(system_report(e2e, retrieval, flags, settings, args.pytest_result), encoding="utf-8")
    print(json.dumps({"answer_cases": sum(row.get("decision") == "ANSWER" for row in e2e.get("scenarios", [])), "flags": dict(flags), "written": {key: str(value) for key, value in paths.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
