#!/usr/bin/env python3
"""Guard: runtime output files must not be git-tracked.

Standard-library only.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Sequence

RUNTIME_OUTPUT_PATTERNS: Sequence[str] = (
    "prompt-dsl-system/tools/guard_report.json",
    "prompt-dsl-system/tools/health_report.json",
    "prompt-dsl-system/tools/health_report.md",
    "prompt-dsl-system/tools/health_runbook.json",
    "prompt-dsl-system/tools/health_runbook.md",
    "prompt-dsl-system/tools/health_runbook.sh",
    "prompt-dsl-system/tools/validate_report.json",
    "prompt-dsl-system/tools/run_plan.yaml",
    "prompt-dsl-system/tools/loop_diagnostics.json",
    "prompt-dsl-system/tools/loop_diagnostics.md",
    "prompt-dsl-system/tools/risk_gate_report.json",
    "prompt-dsl-system/tools/move_report.json",
    "prompt-dsl-system/tools/rollback_report.json",
    "prompt-dsl-system/tools/trace_history.jsonl",
    "prompt-dsl-system/tools/trace_index.json",
    "prompt-dsl-system/tools/trace_index.md",
    "prompt-dsl-system/tools/policy.json",
    "prompt-dsl-system/tools/policy_effective.json",
    "prompt-dsl-system/tools/policy_sources.json",
    "prompt-dsl-system/tools/ops_guard_report.json",
    "prompt-dsl-system/tools/snapshot_index.json",
    "prompt-dsl-system/tools/snapshot_index.md",
    "prompt-dsl-system/tools/snapshot_prune_report.json",
    "prompt-dsl-system/tools/snapshot_prune_report.md",
    "prompt-dsl-system/tools/trace_diff.json",
    "prompt-dsl-system/tools/trace_diff.md",
    "prompt-dsl-system/tools/bisect_plan.json",
    "prompt-dsl-system/tools/bisect_plan.md",
    "prompt-dsl-system/tools/bisect_plan.sh",
    "prompt-dsl-system/tools/conflict_plan.json",
    "prompt-dsl-system/tools/conflict_plan.md",
    "prompt-dsl-system/tools/followup_checklist.md",
    "prompt-dsl-system/tools/followup_patch.diff",
    "prompt-dsl-system/tools/followup_patch_plan.json",
    "prompt-dsl-system/tools/followup_patch_plan.md",
    "prompt-dsl-system/tools/followup_scan_report.json",
    "prompt-dsl-system/tools/followup_verify_report.json",
)

ALLOWLIST_PATTERNS: Sequence[str] = (
    "prompt-dsl-system/tools/tests/**",
    "prompt-dsl-system/tools/testdata/**",
    "prompt-dsl-system/tools/history/**",
    "prompt-dsl-system/tools/artifacts/templates/**",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_rel(path: str) -> str:
    rel = str(path or "").strip().replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def match_any(path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def find_runtime_tracked_outputs(
    tracked_files: Iterable[str],
    runtime_patterns: Sequence[str] = RUNTIME_OUTPUT_PATTERNS,
    allowlist_patterns: Sequence[str] = ALLOWLIST_PATTERNS,
) -> List[str]:
    violations: List[str] = []
    for raw in tracked_files:
        rel = normalize_rel(raw)
        if not rel:
            continue
        if match_any(rel, allowlist_patterns):
            continue
        if match_any(rel, runtime_patterns):
            violations.append(rel)
    return sorted(set(violations))


def git_ls_files(repo_root: Path) -> List[str]:
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(repo_root),
        capture_output=True,
        text=False,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
        raise RuntimeError(f"git ls-files failed: {stderr.strip()}")

    raw = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    return [normalize_rel(x) for x in raw.split("\0") if normalize_rel(x)]


def read_file_list(path: Path) -> List[str]:
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"tracked-file-list not found: {path}")
    return [normalize_rel(line) for line in path.read_text(encoding="utf-8").splitlines() if normalize_rel(line)]


def build_report(repo_root: Path, violations: Sequence[str], tracked_total: int) -> dict:
    return {
        "tool": "runtime_outputs_tracking_guard",
        "tool_version": "1.0.0",
        "generated_at": now_iso(),
        "repo_root": str(repo_root.resolve()),
        "runtime_patterns": list(RUNTIME_OUTPUT_PATTERNS),
        "allowlist_patterns": list(ALLOWLIST_PATTERNS),
        "tracked_total": int(tracked_total),
        "violations_total": int(len(violations)),
        "violations": list(violations),
        "pass": len(violations) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure runtime output files are not git-tracked")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    parser.add_argument(
        "--tracked-file-list",
        default="",
        help="Optional newline file list for tests (skip git ls-files when provided)",
    )
    parser.add_argument("--out-json", default="", help="Optional report json output path")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    try:
        if str(args.tracked_file_list).strip():
            tracked = read_file_list((repo_root / str(args.tracked_file_list)).resolve())
        else:
            tracked = git_ls_files(repo_root)
    except Exception as exc:
        print(f"[runtime_outputs_tracking_guard] ERROR: {exc}", file=sys.stderr)
        return 2

    violations = find_runtime_tracked_outputs(tracked)
    report = build_report(repo_root, violations, tracked_total=len(tracked))

    out_json = str(args.out_json or "").strip()
    if out_json:
        out_path = Path(out_json)
        if not out_path.is_absolute():
            out_path = (repo_root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[runtime_outputs_tracking_guard] report={out_path}")

    if violations:
        print(
            f"[runtime_outputs_tracking_guard] FAIL tracked_runtime_outputs={len(violations)}",
            file=sys.stderr,
        )
        for item in violations[:40]:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("[runtime_outputs_tracking_guard] PASS tracked_runtime_outputs=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
