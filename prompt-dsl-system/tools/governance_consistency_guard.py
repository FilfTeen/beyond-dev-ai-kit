#!/usr/bin/env python3
"""Validate governance document consistency across constitution/compliance/fact baseline."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

EXIT_INVALID_INPUT = 2
EXIT_GUARD_FAIL = 36

MATRIX_ROW_RE = re.compile(r"^\|\s*R(\d{2})\s*\|", re.IGNORECASE)
MATRIX_TITLE_RANGE_RE = re.compile(r"R(\d{2})\s*~\s*R(\d{2})", re.IGNORECASE)
CONSTITUTION_RULE_RE = re.compile(r"^##\s+Rule\s+(\d{2})\s+-", re.IGNORECASE)
FACT_HEADING_RE = re.compile(r"^##\s+\d+\)\s+.*$", re.IGNORECASE)
RID_RE = re.compile(r"R(\d{2})", re.IGNORECASE)


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


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_matrix_ids_and_statuses(text: str) -> Tuple[List[int], List[str], List[int]]:
    ids: List[int] = []
    statuses: List[str] = []
    duplicates: List[int] = []
    seen: Set[int] = set()
    for raw in text.splitlines():
        line = raw.strip()
        m = MATRIX_ROW_RE.match(line)
        if not m:
            continue
        rid = int(m.group(1))
        if rid in seen:
            duplicates.append(rid)
        seen.add(rid)
        ids.append(rid)

        parts = [part.strip() for part in line.split("|")]
        if len(parts) >= 3:
            statuses.append(parts[-2])
    return ids, statuses, duplicates


def extract_matrix_title_range(text: str) -> Tuple[int | None, int | None]:
    for line in text.splitlines():
        if not line.startswith("#"):
            continue
        m = MATRIX_TITLE_RANGE_RE.search(line)
        if m:
            return int(m.group(1)), int(m.group(2))
        break
    return None, None


def extract_constitution_rule_numbers(text: str) -> Tuple[List[int], List[int]]:
    rules: List[int] = []
    duplicates: List[int] = []
    seen: Set[int] = set()
    for raw in text.splitlines():
        m = CONSTITUTION_RULE_RE.match(raw.strip())
        if not m:
            continue
        idx = int(m.group(1))
        if idx in seen:
            duplicates.append(idx)
        seen.add(idx)
        rules.append(idx)
    return rules, duplicates


def extract_fact_heading_r_ids(text: str) -> List[int]:
    ids: Set[int] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not FACT_HEADING_RE.match(line):
            continue
        for rid in RID_RE.findall(line):
            ids.add(int(rid))
    return sorted(ids)


def missing_in_sequence(values: List[int], start: int, end: int) -> List[int]:
    present = set(values)
    return [i for i in range(start, end + 1) if i not in present]


def run_guard(
    repo_root: Path,
    matrix_path: Path,
    constitution_path: Path,
    fact_path: Path,
    require_met_status: bool,
    fact_tail_window: int,
) -> Dict[str, Any]:
    violations: List[str] = []

    matrix_text = read_text(matrix_path)
    constitution_text = read_text(constitution_path)
    fact_text = read_text(fact_path)

    matrix_ids, matrix_statuses, matrix_dups = extract_matrix_ids_and_statuses(matrix_text)
    title_start, title_end = extract_matrix_title_range(matrix_text)
    rule_ids, rule_dups = extract_constitution_rule_numbers(constitution_text)
    fact_ids = extract_fact_heading_r_ids(fact_text)

    if not matrix_ids:
        violations.append("compliance matrix has no requirement rows")
    else:
        matrix_min = min(matrix_ids)
        matrix_max = max(matrix_ids)
        matrix_missing = missing_in_sequence(sorted(set(matrix_ids)), matrix_min, matrix_max)
        if matrix_missing:
            violations.append("compliance matrix requirement ids not contiguous: " + ",".join(f"R{n:02d}" for n in matrix_missing))
        if matrix_dups:
            violations.append("compliance matrix has duplicate requirement ids: " + ",".join(f"R{n:02d}" for n in sorted(set(matrix_dups))))

        if title_end is None:
            violations.append("compliance matrix title range (Rxx~Ryy) missing")
        else:
            if title_end != matrix_max:
                violations.append(
                    f"compliance matrix title max mismatch: title_end=R{title_end:02d} matrix_max=R{matrix_max:02d}"
                )
            if title_start is not None and title_start > title_end:
                violations.append(
                    f"compliance matrix title range invalid: start=R{title_start:02d} end=R{title_end:02d}"
                )

        if require_met_status:
            non_met = sorted({status for status in matrix_statuses if status and status.lower() != "met"})
            if non_met:
                violations.append("compliance matrix contains non-Met status rows: " + ", ".join(non_met))

    if not rule_ids:
        violations.append("constitution has no Rule headings")
    else:
        rule_min = min(rule_ids)
        rule_max = max(rule_ids)
        rule_missing = missing_in_sequence(sorted(set(rule_ids)), rule_min, rule_max)
        if rule_missing:
            violations.append("constitution rule ids not contiguous: " + ",".join(f"Rule {n:02d}" for n in rule_missing))
        if rule_dups:
            violations.append("constitution has duplicate rules: " + ",".join(f"Rule {n:02d}" for n in sorted(set(rule_dups))))

    if not fact_ids:
        violations.append("fact baseline has no heading requirement references")
    elif matrix_ids:
        matrix_max = max(matrix_ids)
        fact_max = max(fact_ids)
        if fact_max != matrix_max:
            violations.append(
                f"fact baseline latest requirement mismatch: fact_max=R{fact_max:02d} matrix_max=R{matrix_max:02d}"
            )

        window = max(1, int(fact_tail_window))
        tail_start = max(min(matrix_ids), matrix_max - window + 1)
        tail_missing = [rid for rid in range(tail_start, matrix_max + 1) if rid not in set(fact_ids)]
        if tail_missing:
            violations.append(
                "fact baseline missing tail requirement coverage: "
                + ",".join(f"R{rid:02d}" for rid in tail_missing)
            )

    checks_total = 8
    checks_passed = checks_total - len(violations)
    if checks_passed < 0:
        checks_passed = 0

    report: Dict[str, Any] = {
        "tool": "governance_consistency_guard",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "inputs": {
            "matrix": str(matrix_path),
            "constitution": str(constitution_path),
            "fact_baseline": str(fact_path),
            "require_met_status": bool(require_met_status),
            "fact_tail_window": int(fact_tail_window),
        },
        "actual": {
            "matrix": {
                "count": len(matrix_ids),
                "min": min(matrix_ids) if matrix_ids else None,
                "max": max(matrix_ids) if matrix_ids else None,
                "title_range_start": title_start,
                "title_range_end": title_end,
            },
            "constitution": {
                "count": len(rule_ids),
                "min": min(rule_ids) if rule_ids else None,
                "max": max(rule_ids) if rule_ids else None,
            },
            "fact_baseline": {
                "heading_requirement_ids": [f"R{rid:02d}" for rid in fact_ids],
                "latest": f"R{max(fact_ids):02d}" if fact_ids else "",
            },
        },
        "violations": violations,
        "summary": {
            "checks_total": checks_total,
            "checks_passed": checks_passed,
            "checks_failed": len(violations),
            "passed": len(violations) == 0,
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate governance document consistency.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument(
        "--matrix",
        default="prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md",
        help="Path to compliance matrix markdown (relative to repo-root by default).",
    )
    parser.add_argument(
        "--constitution",
        default="prompt-dsl-system/00_conventions/HONGZHI_COMPANY_CONSTITUTION.md",
        help="Path to constitution markdown (relative to repo-root by default).",
    )
    parser.add_argument(
        "--fact-baseline",
        default="prompt-dsl-system/00_conventions/FACT_BASELINE.md",
        help="Path to fact baseline markdown (relative to repo-root by default).",
    )
    parser.add_argument(
        "--require-met-status",
        default="true",
        help="true/false; enforce all compliance matrix status values are Met.",
    )
    parser.add_argument(
        "--fact-tail-window",
        type=int,
        default=17,
        help="Contiguous trailing requirement window that must be present in fact baseline headings.",
    )
    parser.add_argument("--out-json", default="")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[governance_consistency] FAIL: invalid repo_root: {repo_root}")
        return EXIT_INVALID_INPUT

    matrix = Path(args.matrix)
    constitution = Path(args.constitution)
    fact = Path(args.fact_baseline)
    if not matrix.is_absolute():
        matrix = (repo_root / matrix).resolve()
    if not constitution.is_absolute():
        constitution = (repo_root / constitution).resolve()
    if not fact.is_absolute():
        fact = (repo_root / fact).resolve()

    for path in (matrix, constitution, fact):
        if not path.is_file():
            print(f"[governance_consistency] FAIL: file not found: {path}")
            return EXIT_INVALID_INPUT

    require_met_status = parse_bool(args.require_met_status, default=True)
    report = run_guard(
        repo_root=repo_root,
        matrix_path=matrix,
        constitution_path=constitution,
        fact_path=fact,
        require_met_status=require_met_status,
        fact_tail_window=args.fact_tail_window,
    )

    out_json = str(args.out_json or "").strip()
    if out_json:
        out_path = Path(out_json).expanduser()
        if not out_path.is_absolute():
            out_path = (repo_root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    passed = bool(summary.get("passed", False))
    checks_passed = int(summary.get("checks_passed", 0))
    checks_total = int(summary.get("checks_total", 0))
    violations = report.get("violations", []) if isinstance(report, dict) else []

    if passed:
        print(f"[governance_consistency] PASS checks={checks_passed}/{checks_total}")
        return 0

    print(
        f"[governance_consistency] FAIL checks={checks_passed}/{checks_total} violations={len(violations)}"
    )
    for item in violations:
        print(f"  - {item}")
    return EXIT_GUARD_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
