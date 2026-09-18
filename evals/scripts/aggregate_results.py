#!/usr/bin/env python3
"""把 judgments_v1.jsonl 聚合成 summary_v1.json（数字全部可由逐题判断复现）。

用法：python3 evals/scripts/aggregate_results.py
"""

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
JUDGMENTS = HERE / "judgments_v1.jsonl"
SUMMARY = HERE / "summary_v1.json"

DIMENSIONS = ["project_understanding", "real_effect", "iteration_improvement",
              "effect_evaluation", "showcase_integrity"]


def wilson(passes: int, total: int, z: float = 1.96) -> list[float] | None:
    if total == 0:
        return None
    p = passes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return [round(center - spread, 4), round(center + spread, 4)]


def main() -> int:
    judgments = [json.loads(line) for line in
                 JUDGMENTS.read_text(encoding="utf-8").splitlines() if line.strip()]

    conditions: dict[str, dict] = {}
    for name in ("baseline", "skill"):
        rows = [j for j in judgments if j.get("condition") == name]
        unique = {j["case_id"] for j in rows}
        passed = sum(1 for j in rows
                     if not j.get("critical_failure") and not j.get("failed_required_checks"))
        dims = {}
        for dim in DIMENSIONS:
            scores = [j["scores"][dim] for j in rows if dim in j.get("scores", {})]
            dims[dim] = round(sum(scores) / len(scores), 3) if scores else None
        conditions[name] = {
            "judgment_count": len(rows),
            "unique_case_count": len(unique),
            "pass_count": passed,
            "pass_rate": round(passed / len(rows), 4) if rows else None,
            "pass_rate_wilson_95": wilson(passed, len(rows)),
            "critical_failure_count": sum(1 for j in rows if j.get("critical_failure")),
            "dimension_means_0_to_4": dims,
        }

    skill = conditions["skill"]["pass_rate"]
    baseline = conditions["baseline"]["pass_rate"]
    summary = {
        "schema_version": "1.0",
        "status": "completed" if conditions["skill"]["judgment_count"] else "not_run",
        "dimensions": DIMENSIONS,
        "conditions": conditions,
        "skill_minus_baseline_pass_rate": (None if skill is None or baseline is None
                                           else round(skill - baseline, 4)),
        "interpretation_note": (
            "A critical failure always fails that judgment; pass otherwise requires all "
            "atomic checks green (script layer) or a mean dimension score of at least "
            "3.0/4.0 (agent layer). 判定为开发 Agent 自评（model_only）。"),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
