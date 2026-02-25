#!/usr/bin/env python3
"""Validate closure artifacts for a development run."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

TOOL = "delivery_closure_guard"
TOOL_VERSION = "1.0.0"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def git_changed_paths(repo_root: Path) -> List[str]:
    cmd = ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=all"]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        return []
    out: List[str] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        payload = line[3:].strip()
        if not payload:
            continue
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1].strip()
        out.append(payload)
    return out


def has_required_section(path: Path, marker: str) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    return marker in text


def run_guard(repo_root: Path) -> dict:
    required_docs = [
        "README.md",
        "EVOLUTION_LOG.md",
        "CHANGELOG.md",
    ]
    required_templates = [
        (
            "prompt-dsl-system/tools/artifacts/templates/kit_self_upgrade/A3_change_ledger.template.md",
            "## File Changes",
        ),
        (
            "prompt-dsl-system/tools/artifacts/templates/kit_self_upgrade/A3_rollback_plan.template.md",
            "## Rollback Trigger",
        ),
        (
            "prompt-dsl-system/tools/artifacts/templates/kit_self_upgrade/A3_cleanup_report.template.md",
            "## Final Status",
        ),
    ]
    doc_update_candidates = {
        "README.md",
        "README.zh-CN.md",
        "CHANGELOG.md",
        "EVOLUTION_LOG.md",
        "prompt-dsl-system/README.md",
        "prompt-dsl-system/00_conventions/FACT_BASELINE.md",
        "prompt-dsl-system/tools/README.md",
    }
    temp_noise_markers = (
        "_regression_tmp/",
        ".tmp",
        ".bak",
        ".orig",
    )

    checks: List[CheckResult] = []

    missing_docs = [item for item in required_docs if not (repo_root / item).is_file()]
    checks.append(
        CheckResult(
            name="required_docs_present",
            passed=not missing_docs,
            detail="missing=" + (",".join(missing_docs) if missing_docs else "none"),
        )
    )

    missing_templates = []
    for rel, marker in required_templates:
        if not has_required_section(repo_root / rel, marker):
            missing_templates.append(rel)
    checks.append(
        CheckResult(
            name="closure_templates_valid",
            passed=not missing_templates,
            detail="missing_or_invalid=" + (",".join(missing_templates) if missing_templates else "none"),
        )
    )

    changed = git_changed_paths(repo_root)
    code_changed = [p for p in changed if p.startswith("prompt-dsl-system/") or p.endswith((".py", ".sh", ".yaml", ".yml", ".json"))]
    docs_changed = [p for p in changed if p in doc_update_candidates]
    docs_ok = (not code_changed) or bool(docs_changed)
    checks.append(
        CheckResult(
            name="closure_docs_updated_when_code_changed",
            passed=docs_ok,
            detail=f"code_changed={len(code_changed)},docs_changed={len(docs_changed)}",
        )
    )

    temp_noise = [p for p in changed if any(marker in p for marker in temp_noise_markers)]
    checks.append(
        CheckResult(
            name="no_temp_noise_in_workspace",
            passed=not temp_noise,
            detail="noise=" + (",".join(temp_noise[:12]) if temp_noise else "none"),
        )
    )

    passed = all(item.passed for item in checks)
    return {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "repo_root": str(repo_root),
        "summary": {
            "passed": passed,
            "checks_total": len(checks),
            "checks_failed": sum(1 for item in checks if not item.passed),
            "changed_files": len(changed),
        },
        "checks": [
            {"name": item.name, "passed": item.passed, "detail": item.detail}
            for item in checks
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run delivery closure guard checks.")
    parser.add_argument("--repo-root", required=True, help="Repository root path")
    parser.add_argument(
        "--out-json",
        default="prompt-dsl-system/tools/delivery_closure_report.json",
        help="Output report JSON path",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[{TOOL}] FAIL: invalid repo root: {repo_root}")
        return 2

    report = run_guard(repo_root=repo_root)
    out_json = Path(args.out_json)
    if not out_json.is_absolute():
        out_json = repo_root / out_json
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if report["summary"]["passed"]:
        print(f"[{TOOL}] PASS: {out_json}")
        return 0
    print(f"[{TOOL}] FAIL: {out_json}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
