#!/usr/bin/env python3
"""Gate kit selfcheck report freshness and repo snapshot consistency."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

EXIT_INVALID_INPUT = 2
EXIT_GATE_FAIL = 28


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


def load_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_iso_utc(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def resolve_report_repo_root(raw: Any, repo_root: Path) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


def run_git(repo_root: Path, args: List[str]) -> Tuple[bool, str]:
    cmd = ["git", "-C", str(repo_root)] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError:
        return False, ""
    if proc.returncode != 0:
        return False, ""
    return True, str(proc.stdout or "").strip()


def current_git_snapshot(repo_root: Path) -> Dict[str, Any]:
    head_ok, head = run_git(repo_root, ["rev-parse", "--verify", "HEAD"])
    status_ok, status = run_git(repo_root, ["status", "--porcelain"])
    status_lines = [line for line in status.splitlines() if line.strip()] if status_ok else []
    return {
        "git_head": head if head_ok else "",
        "git_head_available": bool(head_ok and head),
        "git_dirty": bool(status_lines) if status_ok else False,
        "git_status_available": bool(status_ok),
    }


def build_result(
    report: Dict[str, Any],
    repo_root: Path,
    max_age_seconds: int,
    require_git_head: bool,
) -> Dict[str, Any]:
    violations: List[str] = []
    generated_dt = parse_iso_utc(report.get("generated_at"))
    now_dt = datetime.now(timezone.utc)
    age_seconds: int | None = None
    if generated_dt is None:
        violations.append("generated_at missing or invalid")
    else:
        delta = (now_dt - generated_dt).total_seconds()
        if delta < 0:
            violations.append(f"generated_at is in future: {delta:.3f}s")
        else:
            age_seconds = int(delta)
            if age_seconds > max_age_seconds:
                violations.append(
                    f"report is stale: age_seconds={age_seconds} > max_age_seconds={max_age_seconds}"
                )

    report_repo_root = resolve_report_repo_root(report.get("repo_root"), repo_root)
    if report_repo_root is None:
        violations.append("repo_root missing in report")
    elif report_repo_root != repo_root:
        violations.append(
            f"repo_root mismatch: report={report_repo_root} expected={repo_root}"
        )

    report_snapshot = report.get("repo_snapshot")
    if not isinstance(report_snapshot, dict):
        report_snapshot = {}
        violations.append("repo_snapshot missing in report")

    report_head = str(report_snapshot.get("git_head", "")).strip()
    report_head_available = bool(
        report_snapshot.get("git_head_available", bool(report_head))
    )
    report_dirty_present = "git_dirty" in report_snapshot
    report_dirty = bool(report_snapshot.get("git_dirty", False))

    current_snapshot = current_git_snapshot(repo_root)
    current_head = str(current_snapshot.get("git_head", "")).strip()
    current_head_available = bool(current_snapshot.get("git_head_available", False))
    current_dirty_available = bool(current_snapshot.get("git_status_available", False))
    current_dirty = bool(current_snapshot.get("git_dirty", False))

    if current_head_available:
        if not report_head_available:
            violations.append("report repo_snapshot missing git_head while current repo has HEAD")
        elif report_head != current_head:
            violations.append(
                f"git_head mismatch: report={report_head} current={current_head}"
            )
    elif require_git_head:
        violations.append("git_head unavailable in current repo but require_git_head=true")

    if report_dirty_present and current_dirty_available and report_dirty != current_dirty:
        violations.append(
            f"git_dirty mismatch: report={report_dirty} current={current_dirty}"
        )

    return {
        "passed": len(violations) == 0,
        "threshold": {
            "max_age_seconds": max_age_seconds,
            "require_git_head": require_git_head,
        },
        "actual": {
            "generated_at": report.get("generated_at"),
            "age_seconds": age_seconds,
            "report_repo_root": str(report_repo_root) if report_repo_root else "",
            "expected_repo_root": str(repo_root),
            "report_git_head": report_head,
            "report_git_head_available": report_head_available,
            "current_git_head": current_head,
            "current_git_head_available": current_head_available,
            "report_git_dirty": report_dirty if report_dirty_present else None,
            "current_git_dirty": current_dirty if current_dirty_available else None,
        },
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gate selfcheck report freshness + repo snapshot consistency"
    )
    parser.add_argument("--report-json", required=True, help="Path to kit_selfcheck_report.json")
    parser.add_argument("--repo-root", default=".", help="Expected repository root")
    parser.add_argument(
        "--max-age-seconds",
        type=int,
        default=900,
        help="Maximum allowed age for report.generated_at",
    )
    parser.add_argument(
        "--require-git-head",
        default="false",
        help="true/false; require current repo to have a git HEAD",
    )
    parser.add_argument("--out-json", default="", help="Optional output path for gate result JSON")
    args = parser.parse_args()

    report_path = Path(args.report_json).expanduser().resolve()
    repo_root = Path(args.repo_root).expanduser().resolve()
    max_age_seconds = int(args.max_age_seconds)
    require_git_head = parse_bool(args.require_git_head, default=False)

    if max_age_seconds < 0:
        print(
            f"[selfcheck_freshness] FAIL: max-age-seconds must be >= 0 (got {max_age_seconds})"
        )
        return EXIT_INVALID_INPUT
    if not repo_root.is_dir():
        print(f"[selfcheck_freshness] FAIL: invalid repo-root: {repo_root}")
        return EXIT_INVALID_INPUT
    if not report_path.is_file():
        print(f"[selfcheck_freshness] FAIL: report not found: {report_path}")
        return EXIT_INVALID_INPUT

    report = load_json(report_path)
    if not report:
        print(f"[selfcheck_freshness] FAIL: invalid JSON report: {report_path}")
        return EXIT_INVALID_INPUT

    result = build_result(
        report=report,
        repo_root=repo_root,
        max_age_seconds=max_age_seconds,
        require_git_head=require_git_head,
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
            "[selfcheck_freshness] PASS: "
            f"age_seconds={actual.get('age_seconds')} "
            f"max_age_seconds={threshold['max_age_seconds']} "
            f"head_available={actual.get('current_git_head_available')} "
            f"head_match={actual.get('report_git_head') == actual.get('current_git_head')}"
        )
        if out_json_path is not None:
            print(f"[selfcheck_freshness] report={out_json_path}")
        return 0

    print("[selfcheck_freshness] FAIL")
    for item in result["violations"]:
        print(f"[selfcheck_freshness] violation: {item}")
    if out_json_path is not None:
        print(f"[selfcheck_freshness] report={out_json_path}")
    return EXIT_GATE_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
