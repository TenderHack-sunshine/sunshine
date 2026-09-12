from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter_ns

from build_profanity_benchmark import OUT

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.safety.profanity import RuleProfanityDetector


def percentile(values: list[float], fraction: float) -> float:
    return sorted(values)[min(round((len(values) - 1) * fraction), len(values) - 1)]


def main() -> None:
    rows = [json.loads(line) for line in OUT.read_text(encoding="utf-8").splitlines() if line]
    detector, timings, category = RuleProfanityDetector(), [], defaultdict(lambda: [0, 0])
    counts = Counter()
    for row in rows:
        started = perf_counter_ns()
        actual = detector.detect(row["text"]).detected
        timings.append((perf_counter_ns() - started) / 1_000_000)
        expected = row["expected_profane"]
        if actual and expected: counts["tp"] += 1
        elif actual and not expected: counts["fp"] += 1
        elif not actual and expected: counts["fn"] += 1
        else: counts["tn"] += 1
        if expected:
            category[row["category"]][0] += int(actual)
            category[row["category"]][1] += 1
    precision = counts["tp"] / max(counts["tp"] + counts["fp"], 1)
    recall = counts["tp"] / max(counts["tp"] + counts["fn"], 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    payload = {"cases": len(rows), "TP": counts["tp"], "FP": counts["fp"], "TN": counts["tn"], "FN": counts["fn"],
               "precision": precision, "recall": recall, "f1": f1,
               "per_category_recall": {name: found / total for name, (found, total) in sorted(category.items())},
               "latency_ms": {"mean": statistics.fmean(timings), "p50": percentile(timings, .5), "p95": percentile(timings, .95)}}
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
