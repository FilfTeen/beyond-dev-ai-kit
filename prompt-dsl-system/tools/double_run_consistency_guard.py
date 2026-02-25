#!/usr/bin/env python3
"""Guard: validate/selfcheck double run should not add tracked diffs.

Standard-library only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_git_status_paths(status_text: str) -> Set[str]:
    paths: Set[str] = set()
    for raw in status_text.splitlines():
        line = raw.rstrip("\n")
        if not line or len(line) < 3:
            continue
        status = line[:2]
        if status == "??":
            continue
        entry = line[3:].strip()
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1].strip()
        if entry.startswith('"') and entry.endswith('"') and len(entry) >= 2:
            entry = entry[1:-1]
        entry = entry.replace("\\", "/")
        if entry:
            paths.add(entry)
    return paths


def git_tracked_dirty_paths(repo_root: Path) -> Set[str]:
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git status failed: {proc.stderr.strip()}")
    return parse_git_status_paths(proc.stdout)


def run_cmd(cmd: Sequence[str], cwd: Path) -> Tuple[int, str, str]:
    proc = subprocess.run(
        list(cmd),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def run_validate_selfcheck(repo_root: Path, run_script: Path, validate_module: str) -> Dict[str, object]:
    validate_cmd = ["bash", str(run_script), "validate", "-r", str(repo_root), "-m", str(validate_module)]
    selfcheck_cmd = ["bash", str(run_script), "selfcheck", "-r", str(repo_root)]

    v_rc, v_out, v_err = run_cmd(validate_cmd, repo_root)
    if v_rc != 0:
        return {
            "pass": False,
            "failed_cmd": "validate",
            "rc": v_rc,
            "stdout_tail": v_out.splitlines()[-20:],
            "stderr_tail": v_err.splitlines()[-20:],
        }

    s_rc, s_out, s_err = run_cmd(selfcheck_cmd, repo_root)
    if s_rc != 0:
        return {
            "pass": False,
            "failed_cmd": "selfcheck",
            "rc": s_rc,
            "stdout_tail": s_out.splitlines()[-20:],
            "stderr_tail": s_err.splitlines()[-20:],
        }

    return {
        "pass": True,
        "validate_rc": v_rc,
        "selfcheck_rc": s_rc,
    }


def build_report(
    repo_root: Path,
    baseline: Set[str],
    after_first: Set[str],
    after_second: Set[str],
    first_run: Dict[str, object],
    second_run: Dict[str, object],
) -> Dict[str, object]:
    added_first = sorted(after_first - baseline)
    added_second = sorted(after_second - baseline)
    drift = sorted(after_second.symmetric_difference(after_first))
    ok = bool(first_run.get("pass")) and bool(second_run.get("pass")) and (not added_second) and (not drift)
    return {
        "tool": "double_run_consistency_guard",
        "tool_version": "1.0.0",
        "generated_at": now_iso(),
        "repo_root": str(repo_root.resolve()),
        "baseline_tracked_dirty_count": len(baseline),
        "after_first_tracked_dirty_count": len(after_first),
        "after_second_tracked_dirty_count": len(after_second),
        "added_after_first": added_first,
        "added_after_second": added_second,
        "drift_between_runs": drift,
        "first_run": first_run,
        "second_run": second_run,
        "pass": ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure validate/selfcheck double run does not add tracked diffs")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    parser.add_argument("--run-script", default="prompt-dsl-system/tools/run.sh", help="run.sh path")
    parser.add_argument("--validate-module", default=".", help="module path passed to validate -m")
    parser.add_argument("--out-json", default="", help="optional report output path")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    run_script = Path(args.run_script)
    if not run_script.is_absolute():
        run_script = (repo_root / run_script).resolve()
    if not run_script.exists() or not run_script.is_file():
        print(f"[double_run_consistency_guard] ERROR run script not found: {run_script}", file=sys.stderr)
        return 2

    try:
        baseline = git_tracked_dirty_paths(repo_root)
    except Exception as exc:
        print(f"[double_run_consistency_guard] ERROR: {exc}", file=sys.stderr)
        return 2

    first_run = run_validate_selfcheck(repo_root, run_script, str(args.validate_module))
    if not bool(first_run.get("pass")):
        print(
            f"[double_run_consistency_guard] FAIL first_run {first_run.get('failed_cmd')} rc={first_run.get('rc')}",
            file=sys.stderr,
        )
        return 1

    after_first = git_tracked_dirty_paths(repo_root)

    second_run = run_validate_selfcheck(repo_root, run_script, str(args.validate_module))
    if not bool(second_run.get("pass")):
        print(
            f"[double_run_consistency_guard] FAIL second_run {second_run.get('failed_cmd')} rc={second_run.get('rc')}",
            file=sys.stderr,
        )
        return 1

    after_second = git_tracked_dirty_paths(repo_root)

    report = build_report(repo_root, baseline, after_first, after_second, first_run, second_run)

    out_json = str(args.out_json or "").strip()
    if out_json:
        out_path = Path(out_json)
        if not out_path.is_absolute():
            out_path = (repo_root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[double_run_consistency_guard] report={out_path}")

    if not report["pass"]:
        print(
            "[double_run_consistency_guard] FAIL "
            f"added_after_second={len(report['added_after_second'])} drift={len(report['drift_between_runs'])}",
            file=sys.stderr,
        )
        for item in report["added_after_second"][:30]:
            print(f"  + {item}", file=sys.stderr)
        for item in report["drift_between_runs"][:30]:
            print(f"  ~ {item}", file=sys.stderr)
        return 1

    print("[double_run_consistency_guard] PASS tracked_diff_is_stable=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
