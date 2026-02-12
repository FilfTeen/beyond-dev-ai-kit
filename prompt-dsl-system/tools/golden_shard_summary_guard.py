#!/usr/bin/env python3
"""Enforce golden regression shard report + summary contract."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

EXIT_INVALID_INPUT = 2
EXIT_GUARD_FAIL = 39

REPORT_OVERALL_RE = re.compile(r"^\*\*OVERALL:\s*(PASS|FAIL)\*\*$", re.MULTILINE)
REPORT_CHECKS_RE = re.compile(r"^\*\*(\d+)\s*/\s*(\d+)\*\* checks passed\.\s*$", re.MULTILINE)
SUMMARY_LINE_RE = re.compile(r"^- ([a-zA-Z0-9_-]+):\s*(.*)$")
SUMMARY_OVERALL_RE = re.compile(r"OVERALL:\s*(PASS|FAIL)")
SUMMARY_CHECKS_RE = re.compile(r"(\d+)\s*/\s*(\d+)")


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


def parse_expected_shards(raw: str) -> List[str]:
    items: List[str] = []
    for token in str(raw or "").split(","):
        shard = token.strip().lower()
        if not shard:
            continue
        if shard in items:
            continue
        items.append(shard)
    return items


def read_file(path: Path, violations: List[str], label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        violations.append(f"{label} read error: {path} ({exc})")
        return ""


def parse_report_contract(text: str) -> Dict[str, Any]:
    overall_match = REPORT_OVERALL_RE.search(text)
    checks_match = REPORT_CHECKS_RE.search(text)
    overall = overall_match.group(1) if overall_match else ""

    checks_passed = -1
    checks_total = -1
    if checks_match:
        checks_passed = int(checks_match.group(1))
        checks_total = int(checks_match.group(2))

    return {
        "overall": overall,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
    }


def parse_summary_lines(text: str) -> Dict[str, str]:
    lines: Dict[str, str] = {}
    for raw_line in text.splitlines():
        match = SUMMARY_LINE_RE.match(raw_line.strip())
        if not match:
            continue
        shard = match.group(1).strip().lower()
        body = match.group(2).strip()
        if shard and shard not in lines:
            lines[shard] = body
    return lines


def parse_summary_contract(text: str) -> Dict[str, Any]:
    overall_match = SUMMARY_OVERALL_RE.search(text)
    checks_match = SUMMARY_CHECKS_RE.search(text)
    overall = overall_match.group(1) if overall_match else ""

    checks_passed = -1
    checks_total = -1
    if checks_match:
        checks_passed = int(checks_match.group(1))
        checks_total = int(checks_match.group(2))

    return {
        "overall": overall,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
    }


def run_guard(
    reports_dir: Path,
    summary_path: Path,
    expected_shards: List[str],
    require_overall_pass: bool,
    require_full_check_pass: bool,
) -> Dict[str, Any]:
    violations: List[str] = []
    shard_reports: List[Dict[str, Any]] = []

    summary_text = read_file(summary_path, violations, "summary") if summary_path.is_file() else ""
    if not summary_path.is_file():
        violations.append(f"summary file missing: {summary_path}")
    summary_lines = parse_summary_lines(summary_text) if summary_text else {}

    for shard in expected_shards:
        shard_file = reports_dir / f"golden_{shard}.md"
        shard_item: Dict[str, Any] = {
            "shard": shard,
            "report_path": str(shard_file),
            "summary_line": summary_lines.get(shard, ""),
            "report_overall": "",
            "report_checks_passed": -1,
            "report_checks_total": -1,
            "summary_overall": "",
            "summary_checks_passed": -1,
            "summary_checks_total": -1,
            "passed": False,
            "violations": [],
        }

        local_violations: List[str] = []
        if not shard_file.is_file():
            local_violations.append(f"report missing: {shard_file}")
        else:
            report_text = read_file(shard_file, local_violations, f"report({shard})")
            report_contract = parse_report_contract(report_text)
            shard_item["report_overall"] = report_contract["overall"]
            shard_item["report_checks_passed"] = report_contract["checks_passed"]
            shard_item["report_checks_total"] = report_contract["checks_total"]

            if not report_contract["overall"]:
                local_violations.append(f"report overall marker missing: {shard}")
            elif require_overall_pass and report_contract["overall"] != "PASS":
                local_violations.append(f"report overall not PASS: {shard}")

            if report_contract["checks_total"] <= 0:
                local_violations.append(f"report checks summary missing/invalid: {shard}")
            elif require_full_check_pass and report_contract["checks_passed"] != report_contract["checks_total"]:
                local_violations.append(
                    f"report checks not fully passed: {shard} "
                    f"{report_contract['checks_passed']}/{report_contract['checks_total']}"
                )

        summary_line = summary_lines.get(shard, "")
        if not summary_line:
            local_violations.append(f"summary line missing for shard: {shard}")
        else:
            if "MISSING_REPORT" in summary_line or "MISSING_SUMMARY" in summary_line:
                local_violations.append(f"summary marks missing report/summary: {shard}")
            summary_contract = parse_summary_contract(summary_line)
            shard_item["summary_overall"] = summary_contract["overall"]
            shard_item["summary_checks_passed"] = summary_contract["checks_passed"]
            shard_item["summary_checks_total"] = summary_contract["checks_total"]

            if not summary_contract["overall"]:
                local_violations.append(f"summary overall marker missing: {shard}")
            elif require_overall_pass and summary_contract["overall"] != "PASS":
                local_violations.append(f"summary overall not PASS: {shard}")

            if summary_contract["checks_total"] <= 0:
                local_violations.append(f"summary checks marker missing/invalid: {shard}")
            elif require_full_check_pass and summary_contract["checks_passed"] != summary_contract["checks_total"]:
                local_violations.append(
                    f"summary checks not fully passed: {shard} "
                    f"{summary_contract['checks_passed']}/{summary_contract['checks_total']}"
                )

            report_total = int(shard_item["report_checks_total"])
            summary_total = int(shard_item["summary_checks_total"])
            report_passed = int(shard_item["report_checks_passed"])
            summary_passed = int(shard_item["summary_checks_passed"])
            report_overall = str(shard_item["report_overall"])
            summary_overall = str(shard_item["summary_overall"])
            if report_total > 0 and summary_total > 0:
                if report_total != summary_total or report_passed != summary_passed:
                    local_violations.append(
                        f"summary/report checks mismatch: {shard} "
                        f"report={report_passed}/{report_total} summary={summary_passed}/{summary_total}"
                    )
            if report_overall and summary_overall and report_overall != summary_overall:
                local_violations.append(
                    f"summary/report overall mismatch: {shard} report={report_overall} summary={summary_overall}"
                )

        shard_item["violations"] = local_violations
        shard_item["passed"] = len(local_violations) == 0
        shard_reports.append(shard_item)
        violations.extend(local_violations)

    summary_has_unexpected_missing = any(
        ("MISSING_REPORT" in body or "MISSING_SUMMARY" in body) for body in summary_lines.values()
    )
    if summary_has_unexpected_missing:
        violations.append("summary contains missing markers")

    summary_unexpected_shards: List[str] = []
    for shard in sorted(summary_lines.keys()):
        if shard not in expected_shards:
            summary_unexpected_shards.append(shard)

    report: Dict[str, Any] = {
        "tool": "golden_shard_summary_guard",
        "generated_at": now_iso(),
        "inputs": {
            "reports_dir": str(reports_dir),
            "summary": str(summary_path),
            "expected_shards": expected_shards,
            "require_overall_pass": bool(require_overall_pass),
            "require_full_check_pass": bool(require_full_check_pass),
        },
        "actual": {
            "summary_lines_detected": sorted(summary_lines.keys()),
            "summary_unexpected_shards": summary_unexpected_shards,
            "shard_reports": shard_reports,
        },
        "violations": violations,
        "summary": {
            "checks_total": len(expected_shards),
            "checks_passed": sum(1 for item in shard_reports if bool(item.get("passed", False))),
            "checks_failed": sum(1 for item in shard_reports if not bool(item.get("passed", False))),
            "passed": len(violations) == 0,
        },
    }
    return report


def resolve_path(repo_root: Path, raw: str) -> Path:
    path = Path(str(raw or "").strip()).expanduser()
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Golden shard summary contract guard.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--reports-dir", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--expected-shards", default="early,mid,late")
    parser.add_argument("--require-overall-pass", default="true")
    parser.add_argument("--require-full-check-pass", default="true")
    parser.add_argument("--out-json", default="")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[golden_shard_summary_guard] FAIL invalid repo_root: {repo_root}")
        return EXIT_INVALID_INPUT

    expected_shards = parse_expected_shards(args.expected_shards)
    if not expected_shards:
        print("[golden_shard_summary_guard] FAIL expected_shards is empty")
        return EXIT_INVALID_INPUT

    reports_dir = resolve_path(repo_root, args.reports_dir)
    summary_path = resolve_path(repo_root, args.summary)
    require_overall_pass = parse_bool(args.require_overall_pass, default=True)
    require_full_check_pass = parse_bool(args.require_full_check_pass, default=True)

    report = run_guard(
        reports_dir=reports_dir,
        summary_path=summary_path,
        expected_shards=expected_shards,
        require_overall_pass=require_overall_pass,
        require_full_check_pass=require_full_check_pass,
    )

    out_json = str(args.out_json or "").strip()
    if out_json:
        out_path = resolve_path(repo_root, out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    passed = bool(summary.get("passed", False))
    checks_passed = int(summary.get("checks_passed", 0))
    checks_total = int(summary.get("checks_total", 0))
    violations = report.get("violations", []) if isinstance(report, dict) else []

    if passed:
        print(
            "[golden_shard_summary_guard] PASS "
            f"checks={checks_passed}/{checks_total} shards={','.join(expected_shards)}"
        )
        return 0

    print(f"[golden_shard_summary_guard] FAIL checks={checks_passed}/{checks_total} violations={len(violations)}")
    for item in violations:
        print(f"  - {item}")
    return EXIT_GUARD_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
