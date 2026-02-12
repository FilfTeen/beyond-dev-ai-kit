#!/usr/bin/env python3
"""Validate kit self-upgrade closure templates integrity.

Checks required template files and required section markers.
Standard-library only.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List


REQUIRED_FILES: Dict[str, List[str]] = {
    "prompt-dsl-system/tools/artifacts/templates/kit_self_upgrade/A3_change_ledger.template.md": [
        "## File Changes",
        "## Validation Evidence",
    ],
    "prompt-dsl-system/tools/artifacts/templates/kit_self_upgrade/A3_rollback_plan.template.md": [
        "## Rollback Trigger",
        "## Steps",
    ],
    "prompt-dsl-system/tools/artifacts/templates/kit_self_upgrade/A3_cleanup_report.template.md": [
        "## Safety Check",
        "## Final Status",
    ],
}


def _count_placeholders(text: str) -> int:
    count = 0
    in_token = False
    for ch in text:
        if ch == "<":
            in_token = True
        elif ch == ">" and in_token:
            count += 1
            in_token = False
    return count


def run_guard(repo_root: Path) -> int:
    failures: List[str] = []
    for rel_path, markers in REQUIRED_FILES.items():
        fp = repo_root / rel_path
        if not fp.is_file():
            failures.append(f"missing_file:{rel_path}")
            continue
        text = fp.read_text(encoding="utf-8", errors="ignore")
        for marker in markers:
            if marker not in text:
                failures.append(f"missing_marker:{rel_path}:{marker}")
        if _count_placeholders(text) <= 0:
            failures.append(f"missing_placeholder_tokens:{rel_path}")

    if failures:
        print("[template_guard] FAIL")
        for item in failures:
            print(f"[template_guard] {item}")
        return 2

    print("[template_guard] PASS")
    print(f"[template_guard] files_checked={len(REQUIRED_FILES)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="kit_self_upgrade_template_guard.py",
        description="Check A3 closure templates existence and required sections.",
    )
    parser.add_argument("--repo-root", required=True, help="Repository root path")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[template_guard] FAIL: invalid repo-root: {repo_root}")
        return 2

    return run_guard(repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
