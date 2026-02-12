#!/usr/bin/env python3
"""Performance budget guard for core toolkit gates."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Tuple

EXIT_INVALID_INPUT = 2
EXIT_GUARD_FAIL = 41

DEFAULT_HISTORY_FILE = "prompt-dsl-system/tools/performance_history.jsonl"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def run_timed(cmd: List[str]) -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        elapsed = time.perf_counter() - start
        return {
            "returncode": 127,
            "seconds": elapsed,
            "stdout": "",
            "stderr": str(exc),
        }
    elapsed = time.perf_counter() - start
    return {
        "returncode": int(proc.returncode),
        "seconds": elapsed,
        "stdout": str(proc.stdout or ""),
        "stderr": str(proc.stderr or ""),
    }


def resolve_path(repo_root: Path, raw: str) -> Path:
    text = str(raw or "").strip()
    path = Path(text if text else DEFAULT_HISTORY_FILE).expanduser()
    if not path.is_absolute():
        return (repo_root / path).resolve()
    return path.resolve()


def load_history_records(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    records: List[Dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return records
    for line in lines:
        raw = str(line).strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def extract_seconds_map(record: Dict[str, Any]) -> Tuple[float | None, Dict[str, float]]:
    actual = record.get("actual")
    if not isinstance(actual, dict):
        return None, {}
    total_raw = actual.get("total_seconds")
    total: float | None = None
    if isinstance(total_raw, (int, float)):
        total = float(total_raw)

    check_map: Dict[str, float] = {}
    checks = actual.get("checks")
    if isinstance(checks, list):
        for item in checks:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            sec = item.get("seconds")
            if not name or not isinstance(sec, (int, float)):
                continue
            check_map[name] = float(sec)
    return total, check_map


def is_pass_record(record: Dict[str, Any]) -> bool:
    summary = record.get("summary")
    if not isinstance(summary, dict):
        return False
    return bool(summary.get("passed", False))


def evaluate_trend(
    current_results: List[Dict[str, Any]],
    current_total: float,
    history_records: List[Dict[str, Any]],
    window: int,
    min_samples: int,
    max_ratio: float,
    enforce: bool,
) -> Tuple[Dict[str, Any], List[str]]:
    violations: List[str] = []

    passed_history = [record for record in history_records if is_pass_record(record)]
    if window > 0:
        passed_history = passed_history[-window:]

    total_samples: List[float] = []
    per_check_samples: Dict[str, List[float]] = {}
    for record in passed_history:
        total, check_map = extract_seconds_map(record)
        if isinstance(total, float) and total > 0:
            total_samples.append(total)
        for name, sec in check_map.items():
            if sec <= 0:
                continue
            per_check_samples.setdefault(name, []).append(sec)

    trend: Dict[str, Any] = {
        "enforce": bool(enforce),
        "window": int(window),
        "min_samples": int(min_samples),
        "max_ratio": float(max_ratio),
        "samples_available": len(passed_history),
        "total": {
            "samples": len(total_samples),
            "baseline_median_seconds": None,
            "current_seconds": round(current_total, 6),
            "ratio": None,
            "degraded": False,
        },
        "checks": [],
    }

    if len(total_samples) >= max(1, int(min_samples)):
        baseline_total = float(median(total_samples))
        ratio_total = (current_total / baseline_total) if baseline_total > 0 else None
        degraded_total = bool(ratio_total is not None and ratio_total > max_ratio)
        trend["total"] = {
            "samples": len(total_samples),
            "baseline_median_seconds": round(baseline_total, 6),
            "current_seconds": round(current_total, 6),
            "ratio": round(float(ratio_total), 6) if ratio_total is not None else None,
            "degraded": degraded_total,
        }
        if enforce and degraded_total:
            violations.append(
                "trend total regression: "
                f"current={current_total:.3f}s baseline_median={baseline_total:.3f}s ratio={ratio_total:.3f} limit={max_ratio:.3f}"
            )

    for item in current_results:
        name = str(item.get("name", "")).strip()
        current_sec_raw = item.get("seconds")
        if not name or not isinstance(current_sec_raw, (int, float)):
            continue
        current_sec = float(current_sec_raw)
        values = per_check_samples.get(name, [])
        row: Dict[str, Any] = {
            "name": name,
            "samples": len(values),
            "baseline_median_seconds": None,
            "current_seconds": round(current_sec, 6),
            "ratio": None,
            "degraded": False,
        }
        if len(values) >= max(1, int(min_samples)):
            baseline = float(median(values))
            ratio = (current_sec / baseline) if baseline > 0 else None
            degraded = bool(ratio is not None and ratio > max_ratio)
            row["baseline_median_seconds"] = round(baseline, 6)
            row["ratio"] = round(float(ratio), 6) if ratio is not None else None
            row["degraded"] = degraded
            if enforce and degraded:
                violations.append(
                    "trend check regression: "
                    f"{name} current={current_sec:.3f}s baseline_median={baseline:.3f}s ratio={ratio:.3f} limit={max_ratio:.3f}"
                )
        trend["checks"].append(row)

    return trend, violations


def append_history(path: Path, report: Dict[str, Any]) -> str:
    snapshot = {
        "tool": report.get("tool", "performance_budget_guard"),
        "generated_at": report.get("generated_at", now_iso()),
        "summary": report.get("summary", {}),
        "actual": report.get("actual", {}),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError as exc:
        return str(exc)
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Performance budget guard for key gate commands.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--max-selfcheck-seconds", type=float, default=15.0)
    parser.add_argument("--max-governance-seconds", type=float, default=10.0)
    parser.add_argument("--max-syntax-seconds", type=float, default=25.0)
    parser.add_argument("--max-trust-coverage-seconds", type=float, default=10.0)
    parser.add_argument("--max-total-seconds", type=float, default=70.0)
    parser.add_argument("--history-file", default=DEFAULT_HISTORY_FILE)
    parser.add_argument("--history-window", type=int, default=30)
    parser.add_argument("--trend-min-samples", type=int, default=5)
    parser.add_argument("--trend-max-ratio", type=float, default=1.8)
    parser.add_argument("--trend-enforce", default="false")
    parser.add_argument("--history-write", default="true")
    parser.add_argument("--out-json", default="")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[performance_guard] FAIL: invalid repo_root: {repo_root}")
        return EXIT_INVALID_INPUT

    history_file = resolve_path(repo_root, str(args.history_file))
    trend_enforce = parse_bool(args.trend_enforce, default=False)
    history_write = parse_bool(args.history_write, default=True)
    history_window = max(0, int(args.history_window))
    trend_min_samples = max(1, int(args.trend_min_samples))
    trend_max_ratio = float(args.trend_max_ratio)
    if trend_max_ratio <= 1.0:
        print(
            f"[performance_guard] FAIL: trend-max-ratio must be > 1.0, got {trend_max_ratio}"
        )
        return EXIT_INVALID_INPUT

    py = "/usr/bin/python3"
    with tempfile.TemporaryDirectory(prefix="hz_perf_guard_") as td:
        tmp = Path(td).resolve()
        selfcheck_json = tmp / "selfcheck.json"
        selfcheck_md = tmp / "selfcheck.md"

        checks = [
            {
                "name": "kit_selfcheck",
                "limit": float(args.max_selfcheck_seconds),
                "cmd": [
                    py,
                    str(repo_root / "prompt-dsl-system/tools/kit_selfcheck.py"),
                    "--repo-root",
                    str(repo_root),
                    "--out-json",
                    str(selfcheck_json),
                    "--out-md",
                    str(selfcheck_md),
                ],
            },
            {
                "name": "governance_consistency_guard",
                "limit": float(args.max_governance_seconds),
                "cmd": [
                    py,
                    str(repo_root / "prompt-dsl-system/tools/governance_consistency_guard.py"),
                    "--repo-root",
                    str(repo_root),
                ],
            },
            {
                "name": "tool_syntax_guard",
                "limit": float(args.max_syntax_seconds),
                "cmd": [
                    py,
                    str(repo_root / "prompt-dsl-system/tools/tool_syntax_guard.py"),
                    "--repo-root",
                    str(repo_root),
                ],
            },
            {
                "name": "pipeline_trust_coverage_guard",
                "limit": float(args.max_trust_coverage_seconds),
                "cmd": [
                    py,
                    str(repo_root / "prompt-dsl-system/tools/pipeline_trust_coverage_guard.py"),
                    "--repo-root",
                    str(repo_root),
                ],
            },
        ]

        results: List[Dict[str, Any]] = []
        violations: List[str] = []

        for check in checks:
            result = run_timed(check["cmd"])  # type: ignore[index]
            elapsed = float(result.get("seconds", 0.0))
            rc = int(result.get("returncode", 1))
            limit = float(check["limit"])  # type: ignore[index]
            item = {
                "name": str(check["name"]),
                "seconds": round(elapsed, 6),
                "limit_seconds": limit,
                "returncode": rc,
                "passed": rc == 0 and elapsed <= limit,
            }
            if rc != 0:
                stderr = (str(result.get("stderr", "")) + "\n" + str(result.get("stdout", ""))).strip()
                item["error"] = stderr[:600]
                violations.append(f"{check['name']} exited non-zero: {rc}")
            elif elapsed > limit:
                violations.append(
                    f"{check['name']} exceeded budget: seconds={elapsed:.3f} limit={limit:.3f}"
                )
            results.append(item)

    total_seconds = sum(float(x.get("seconds", 0.0)) for x in results)
    if total_seconds > float(args.max_total_seconds):
        violations.append(
            f"total budget exceeded: seconds={total_seconds:.3f} limit={float(args.max_total_seconds):.3f}"
        )

    history_records = load_history_records(history_file)
    trend, trend_violations = evaluate_trend(
        current_results=results,
        current_total=total_seconds,
        history_records=history_records,
        window=history_window,
        min_samples=trend_min_samples,
        max_ratio=trend_max_ratio,
        enforce=trend_enforce,
    )
    if trend_violations:
        violations.extend(trend_violations)

    passed = len(violations) == 0
    report: Dict[str, Any] = {
        "tool": "performance_budget_guard",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "threshold": {
            "max_selfcheck_seconds": float(args.max_selfcheck_seconds),
            "max_governance_seconds": float(args.max_governance_seconds),
            "max_syntax_seconds": float(args.max_syntax_seconds),
            "max_trust_coverage_seconds": float(args.max_trust_coverage_seconds),
            "max_total_seconds": float(args.max_total_seconds),
        },
        "actual": {
            "total_seconds": round(total_seconds, 6),
            "checks": results,
        },
        "trend": trend,
        "history": {
            "file": str(history_file),
            "records_loaded": len(history_records),
            "history_window": history_window,
            "history_write": bool(history_write),
        },
        "violations": violations,
        "summary": {
            "passed": bool(passed),
            "checks_total": len(results),
            "checks_failed": len([x for x in results if not bool(x.get("passed", False))]),
            "trend_enforced": bool(trend_enforce),
        },
    }

    history_write_error = ""
    if history_write:
        history_write_error = append_history(history_file, report)
        if history_write_error:
            report["history"]["write_error"] = history_write_error

    out_json = str(args.out_json or "").strip()
    if out_json:
        out_path = Path(out_json).expanduser()
        if not out_path.is_absolute():
            out_path = (repo_root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if passed:
        print(
            f"[performance_guard] PASS checks={len(results)}/{len(results)} "
            f"total_seconds={total_seconds:.3f}"
        )
        return 0

    print(
        f"[performance_guard] FAIL checks={len(results) - len([x for x in results if not bool(x.get('passed', False))])}/{len(results)} "
        f"total_seconds={total_seconds:.3f}"
    )
    for item in violations:
        print(f"[performance_guard] violation: {item}")
    return EXIT_GUARD_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
