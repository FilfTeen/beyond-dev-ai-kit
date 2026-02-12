#!/usr/bin/env python3
"""Gate kit selfcheck report against quality thresholds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

EXIT_INVALID_INPUT = 2
EXIT_GATE_FAIL = 27
LEVEL_RANK = {
    "low": 0,
    "medium": 1,
    "high": 2,
}
DEFAULT_REQUIRED_DIMENSIONS = [
    "generality",
    "completeness",
    "robustness",
    "efficiency",
    "extensibility",
    "security_governance",
    "kit_mainline_focus",
]


def parse_level(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    return text if text in LEVEL_RANK else "low"


def parse_report(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def get_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def get_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_dimensions_list(raw: str) -> List[str]:
    ordered: List[str] = []
    seen = set()
    for part in str(raw or "").split(","):
        name = str(part).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def collect_dimension_levels(dimensions: Any) -> Tuple[int, List[str], List[str]]:
    if not isinstance(dimensions, dict):
        return 0, [], []

    low_dimensions: List[str] = []
    dim_names = sorted(str(k) for k in dimensions.keys())
    for key in sorted(dimensions.keys()):
        item = dimensions.get(key)
        if not isinstance(item, dict):
            continue
        level = parse_level(item.get("level"))
        if level == "low":
            low_dimensions.append(str(key))

    return len(dimensions), low_dimensions, dim_names


def build_result(
    report: Dict[str, Any],
    min_overall_score: float,
    min_overall_level: str,
    max_low_dimensions: int,
    required_dimensions: List[str],
) -> Dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    dimensions = report.get("dimensions")

    overall_score = get_float(summary.get("overall_score"), 0.0)
    overall_level = parse_level(summary.get("overall_level"))
    summary_dimension_count = get_int(summary.get("dimension_count"))
    dimension_count, low_dimensions, dimension_names = collect_dimension_levels(dimensions)
    dimension_name_set = set(dimension_names)
    missing_required_dimensions = [x for x in required_dimensions if x not in dimension_name_set]

    violations: List[str] = []

    if overall_score < min_overall_score:
        violations.append(
            f"overall_score too low: {overall_score:.3f} < {min_overall_score:.3f}"
        )

    if LEVEL_RANK.get(overall_level, 0) < LEVEL_RANK.get(min_overall_level, 0):
        violations.append(
            f"overall_level too low: {overall_level} < {min_overall_level}"
        )

    if len(low_dimensions) > max_low_dimensions:
        joined = ", ".join(low_dimensions)
        violations.append(
            "low dimension count exceeded: "
            f"{len(low_dimensions)} > {max_low_dimensions} ({joined})"
        )

    if missing_required_dimensions:
        violations.append(
            "required dimensions missing: " + ", ".join(missing_required_dimensions)
        )

    if summary_dimension_count is None:
        violations.append("summary.dimension_count missing or invalid")
    elif summary_dimension_count != dimension_count:
        violations.append(
            "summary.dimension_count mismatch: "
            f"{summary_dimension_count} != {dimension_count}"
        )

    if dimension_count == 0:
        violations.append("dimensions missing or empty")

    result = {
        "passed": len(violations) == 0,
        "threshold": {
            "min_overall_score": round(min_overall_score, 3),
            "min_overall_level": min_overall_level,
            "max_low_dimensions": max_low_dimensions,
            "required_dimensions": required_dimensions,
        },
        "actual": {
            "overall_score": round(overall_score, 3),
            "overall_level": overall_level,
            "summary_dimension_count": summary_dimension_count,
            "dimension_count": dimension_count,
            "dimensions": dimension_names,
            "low_dimensions": low_dimensions,
            "low_dimension_count": len(low_dimensions),
            "missing_required_dimensions": missing_required_dimensions,
        },
        "violations": violations,
    }

    recs = report.get("recommendations")
    if isinstance(recs, list):
        result["recommendations"] = [str(x) for x in recs][:10]
    else:
        result["recommendations"] = []

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gate kit selfcheck report against minimum quality thresholds"
    )
    parser.add_argument("--report-json", required=True, help="Path to kit_selfcheck_report.json")
    parser.add_argument(
        "--min-overall-score",
        type=float,
        default=0.85,
        help="Minimum acceptable overall score",
    )
    parser.add_argument(
        "--min-overall-level",
        choices=sorted(LEVEL_RANK.keys()),
        default="high",
        help="Minimum acceptable overall level",
    )
    parser.add_argument(
        "--max-low-dimensions",
        type=int,
        default=0,
        help="Maximum allowed count of low-level dimensions",
    )
    parser.add_argument(
        "--out-json",
        default="",
        help="Optional output path for gate result JSON",
    )
    parser.add_argument(
        "--required-dimensions",
        default=",".join(DEFAULT_REQUIRED_DIMENSIONS),
        help="Comma-separated required dimensions in selfcheck report",
    )
    args = parser.parse_args()

    report_path = Path(args.report_json).expanduser().resolve()
    if not report_path.is_file():
        print(f"[selfcheck_gate] FAIL: report not found: {report_path}")
        return EXIT_INVALID_INPUT

    min_overall_score = float(args.min_overall_score)
    max_low_dimensions = int(args.max_low_dimensions)
    if min_overall_score < 0.0 or min_overall_score > 1.0:
        print(
            f"[selfcheck_gate] FAIL: min-overall-score out of range [0,1]: {min_overall_score}"
        )
        return EXIT_INVALID_INPUT
    if max_low_dimensions < 0:
        print(f"[selfcheck_gate] FAIL: max-low-dimensions must be >=0: {max_low_dimensions}")
        return EXIT_INVALID_INPUT
    required_dimensions = parse_dimensions_list(args.required_dimensions)
    if not required_dimensions:
        print("[selfcheck_gate] FAIL: required-dimensions is empty")
        return EXIT_INVALID_INPUT

    report = parse_report(report_path)
    if not report:
        print(f"[selfcheck_gate] FAIL: invalid JSON report: {report_path}")
        return EXIT_INVALID_INPUT

    result = build_result(
        report,
        min_overall_score=min_overall_score,
        min_overall_level=args.min_overall_level,
        max_low_dimensions=max_low_dimensions,
        required_dimensions=required_dimensions,
    )

    out_json_path: Path | None = None
    if args.out_json:
        out_json_path = Path(args.out_json).expanduser().resolve()
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    actual = result["actual"]
    threshold = result["threshold"]

    if result["passed"]:
        print(
            "[selfcheck_gate] PASS: "
            f"score={actual['overall_score']:.3f} "
            f"level={actual['overall_level']} "
            f"low_dimensions={actual['low_dimension_count']} "
            f"required_dimensions_ok={len(required_dimensions) - len(actual['missing_required_dimensions'])}/{len(required_dimensions)} "
            f"threshold(score>={threshold['min_overall_score']:.3f}, "
            f"level>={threshold['min_overall_level']}, "
            f"low<={threshold['max_low_dimensions']})"
        )
        if out_json_path is not None:
            print(f"[selfcheck_gate] report={out_json_path}")
        return 0

    print(
        "[selfcheck_gate] FAIL: "
        f"score={actual['overall_score']:.3f} "
        f"level={actual['overall_level']} "
        f"low_dimensions={actual['low_dimension_count']}"
    )
    for msg in result["violations"]:
        print(f"[selfcheck_gate] violation: {msg}")

    recs = result.get("recommendations")
    if isinstance(recs, list) and recs:
        for rec in recs[:3]:
            print(f"[selfcheck_gate] recommendation: {rec}")

    if out_json_path is not None:
        print(f"[selfcheck_gate] report={out_json_path}")
    return EXIT_GATE_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
