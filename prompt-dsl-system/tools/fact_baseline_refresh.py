#!/usr/bin/env python3
"""Refresh FACT_BASELINE key counters from current repository facts.

This tool intentionally updates only high-churn summary lines to avoid
rewriting the full historical baseline narrative.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

TOOL = "fact_baseline_refresh"
TOOL_VERSION = "1.0.0"

FACT_REL = "prompt-dsl-system/00_conventions/FACT_BASELINE.md"
SKILLS_REL = "prompt-dsl-system/05_skill_registry/skills.json"
PIPELINE_DIR_REL = "prompt-dsl-system/04_ai_pipeline_orchestration"


def load_skills(skills_path: Path) -> list[dict]:
    try:
        data = json.loads(skills_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - runtime guard
        raise RuntimeError(f"failed to parse skills registry: {skills_path}") from exc
    if not isinstance(data, list):
        raise RuntimeError("skills registry must be a JSON array")
    return [item for item in data if isinstance(item, dict)]


def count_dimension(repo_root: Path) -> int:
    try:
        from kit_selfcheck import run_selfcheck  # local tool import

        report = run_selfcheck(repo_root)
        summary = report.get("summary", {}) if isinstance(report, dict) else {}
        value = int(summary.get("dimension_count", 0))
        return value if value > 0 else 8
    except Exception:
        return 8


def replace_or_insert(lines: list[str], pattern: str, replacement: str, insert_after: str | None = None) -> None:
    regex = re.compile(pattern)
    for idx, line in enumerate(lines):
        if regex.search(line):
            lines[idx] = replacement
            return
    if insert_after is None:
        lines.append(replacement)
        return
    for idx, line in enumerate(lines):
        if insert_after in line:
            lines.insert(idx + 1, replacement)
            return
    lines.append(replacement)


def format_counter(counter: Counter[str]) -> str:
    if not counter:
        return ""
    return ", ".join(f"{key}={counter[key]}" for key in sorted(counter))


def refresh_fact_baseline(repo_root: Path, fact_path: Path) -> dict:
    skills = load_skills(repo_root / SKILLS_REL)
    domain_counter = Counter(str(item.get("domain", "unknown")) for item in skills)
    status_counter = Counter(str(item.get("status", "unknown")) for item in skills)

    pipeline_dir = repo_root / PIPELINE_DIR_REL
    pipeline_count = len([p for p in pipeline_dir.glob("pipeline_*.md") if p.is_file()])
    dimension_count = count_dimension(repo_root)

    text = fact_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    generated = datetime.now().strftime("%Y-%m-%d")

    replace_or_insert(lines, r"^Generated at:\s+.*$", f"Generated at: {generated} (local)")
    replace_or_insert(lines, r"^- Active skills count:\s+`[0-9]+`$", f"- Active skills count: `{len(skills)}`")
    replace_or_insert(
        lines,
        r"^- Domain distribution:\s+`.*`$",
        f"- Domain distribution: `{format_counter(domain_counter)}`",
    )
    replace_or_insert(
        lines,
        r"^- Skill lifecycle distribution:\s+`.*`$",
        f"- Skill lifecycle distribution: `{format_counter(status_counter)}`",
        insert_after="- Domain distribution:",
    )
    replace_or_insert(
        lines,
        r"^- Pipeline files \(`pipeline_\*\.md`\) count:\s+`[0-9]+`$",
        f"- Pipeline files (`pipeline_*.md`) count: `{pipeline_count}`",
    )
    replace_or_insert(
        lines,
        r"^- `kit_selfcheck\.py`: .* across [0-9]+ dimensions .*",
        f"- `kit_selfcheck.py`: outputs toolkit quality scorecards (`kit_selfcheck_report.json` + `.md`) across {dimension_count} dimensions with missing-path recommendations",
    )

    fact_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "fact_path": str(fact_path),
        "skills_total": len(skills),
        "skills_domain": dict(sorted(domain_counter.items())),
        "skills_status": dict(sorted(status_counter.items())),
        "pipelines_total": pipeline_count,
        "dimension_count": dimension_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh FACT_BASELINE summary counters.")
    parser.add_argument("--repo-root", required=True, help="Repository root path")
    parser.add_argument("--fact-file", default=FACT_REL, help="FACT baseline markdown path")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    fact_path = Path(args.fact_file)
    if not fact_path.is_absolute():
        fact_path = (repo_root / fact_path).resolve()

    if not repo_root.is_dir():
        print(f"[{TOOL}] FAIL: invalid repo root: {repo_root}")
        return 2
    if not fact_path.is_file():
        print(f"[{TOOL}] FAIL: fact file not found: {fact_path}")
        return 2

    report = refresh_fact_baseline(repo_root=repo_root, fact_path=fact_path)
    print(f"[{TOOL}] PASS: {report['fact_path']}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
