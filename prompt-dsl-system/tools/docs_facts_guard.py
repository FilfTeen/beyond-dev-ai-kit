#!/usr/bin/env python3
"""Validate key doc fact lines against repository source-of-truth."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

TOOL = "docs_facts_guard"
TOOL_VERSION = "1.0.0"

README_REL = "README.md"
FACT_REL = "prompt-dsl-system/00_conventions/FACT_BASELINE.md"
SKILLS_REL = "prompt-dsl-system/05_skill_registry/skills.json"
PIPELINE_DIR_REL = "prompt-dsl-system/04_ai_pipeline_orchestration"
GOLDEN_REL = "prompt-dsl-system/tools/golden_path_regression.sh"

README_SKILL_RE = re.compile(r"05_skill_registry\s*\((\d+)\s+skills\)", re.IGNORECASE)
README_PIPELINE_RE = re.compile(r"04_pipeline_orchestration\s*\((\d+)\s+pipelines\)", re.IGNORECASE)
README_GOLDEN_RE = re.compile(r"golden_path_regression\.sh<br/>\((\d+)\s+checks\)", re.IGNORECASE)

FACT_SKILL_COUNT_RE = re.compile(r"^- Active skills count:\s+`(\d+)`$", re.MULTILINE)
FACT_PIPELINE_COUNT_RE = re.compile(r"^- Pipeline files \(`pipeline_\*\.md`\) count:\s+`(\d+)`$", re.MULTILINE)
FACT_LIFECYCLE_RE = re.compile(r"^- Skill lifecycle distribution:\s+`([^`]+)`$", re.MULTILINE)
FACT_GOLDEN_RE = re.compile(r"golden_path_regression\.sh.*\((\d+)\s+checks", re.IGNORECASE)
GOLDEN_CHECK_RE = re.compile(r'check\s+"([^"]+)"\s+"(?:PASS|FAIL)"')


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_skills(path: Path) -> List[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("skills.json must be JSON array")
    return [item for item in data if isinstance(item, dict)]


def parse_distribution(text: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for part in str(text or "").split(","):
        seg = part.strip()
        if not seg or "=" not in seg:
            continue
        key, raw = seg.split("=", 1)
        key = key.strip()
        try:
            value = int(raw.strip())
        except ValueError:
            continue
        if key:
            out[key] = value
    return out


def expected_facts(repo_root: Path) -> Dict[str, object]:
    skills = load_skills(repo_root / SKILLS_REL)
    pipelines = [p for p in (repo_root / PIPELINE_DIR_REL).glob("pipeline_*.md") if p.is_file()]
    status_counter = Counter(str(item.get("status", "unknown")) for item in skills)
    lifecycle = {k: status_counter[k] for k in sorted(status_counter) if int(status_counter[k]) > 0}

    golden_text = (repo_root / GOLDEN_REL).read_text(encoding="utf-8", errors="ignore")
    golden_checks = len(set(GOLDEN_CHECK_RE.findall(golden_text)))

    return {
        "skills_total": len(skills),
        "pipelines_total": len(pipelines),
        "lifecycle": lifecycle,
        "golden_checks": golden_checks,
    }


def _match_int(regex: re.Pattern[str], text: str) -> int | None:
    match = regex.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def run_guard(repo_root: Path) -> dict:
    readme_path = repo_root / README_REL
    fact_path = repo_root / FACT_REL
    expected = expected_facts(repo_root)

    violations: List[str] = []
    checks: List[Dict[str, object]] = []

    if not readme_path.is_file():
        violations.append(f"missing file: {README_REL}")
        readme_text = ""
    else:
        readme_text = readme_path.read_text(encoding="utf-8", errors="ignore")

    if not fact_path.is_file():
        violations.append(f"missing file: {FACT_REL}")
        fact_text = ""
    else:
        fact_text = fact_path.read_text(encoding="utf-8", errors="ignore")

    def add_int_check(name: str, actual: int | None, expected_value: int, source: str) -> None:
        passed = actual == expected_value
        checks.append(
            {
                "name": name,
                "source": source,
                "actual": actual,
                "expected": expected_value,
                "passed": passed,
            }
        )
        if not passed:
            violations.append(f"{name} mismatch: expected={expected_value} actual={actual}")

    add_int_check(
        name="readme_skill_count",
        actual=_match_int(README_SKILL_RE, readme_text),
        expected_value=int(expected["skills_total"]),
        source=README_REL,
    )
    add_int_check(
        name="readme_pipeline_count",
        actual=_match_int(README_PIPELINE_RE, readme_text),
        expected_value=int(expected["pipelines_total"]),
        source=README_REL,
    )
    add_int_check(
        name="readme_golden_check_count",
        actual=_match_int(README_GOLDEN_RE, readme_text),
        expected_value=int(expected["golden_checks"]),
        source=README_REL,
    )
    add_int_check(
        name="fact_skill_count",
        actual=_match_int(FACT_SKILL_COUNT_RE, fact_text),
        expected_value=int(expected["skills_total"]),
        source=FACT_REL,
    )
    add_int_check(
        name="fact_pipeline_count",
        actual=_match_int(FACT_PIPELINE_COUNT_RE, fact_text),
        expected_value=int(expected["pipelines_total"]),
        source=FACT_REL,
    )
    add_int_check(
        name="fact_golden_check_count",
        actual=_match_int(FACT_GOLDEN_RE, fact_text),
        expected_value=int(expected["golden_checks"]),
        source=FACT_REL,
    )

    lifecycle_match = FACT_LIFECYCLE_RE.search(fact_text)
    lifecycle_actual = parse_distribution(lifecycle_match.group(1) if lifecycle_match else "")
    lifecycle_expected = dict(expected["lifecycle"])
    lifecycle_ok = lifecycle_actual == lifecycle_expected
    checks.append(
        {
            "name": "fact_skill_lifecycle_distribution",
            "source": FACT_REL,
            "actual": lifecycle_actual,
            "expected": lifecycle_expected,
            "passed": lifecycle_ok,
        }
    )
    if not lifecycle_ok:
        violations.append(
            "fact lifecycle distribution mismatch: "
            f"expected={lifecycle_expected} actual={lifecycle_actual}"
        )

    passed = len(violations) == 0
    return {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "summary": {
            "passed": passed,
            "checks_total": len(checks),
            "checks_failed": sum(1 for item in checks if not bool(item.get("passed"))),
        },
        "expected": expected,
        "checks": checks,
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate README/FACT key facts against repository data.")
    parser.add_argument("--repo-root", required=True, help="Repository root")
    parser.add_argument(
        "--out-json",
        default="prompt-dsl-system/tools/docs_facts_report.json",
        help="Output report path",
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

    if bool(report.get("summary", {}).get("passed", False)):
        print(f"[{TOOL}] PASS: {out_json}")
        return 0
    print(f"[{TOOL}] FAIL: {out_json}")
    for item in report.get("violations", []):
        print(f"  - {item}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

