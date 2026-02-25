#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

TEST_DIR = Path(__file__).resolve().parent
TOOLS_DIR = TEST_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from docs_facts_guard import run_guard


def _golden_stub(check_count: int) -> str:
    lines = ["#!/usr/bin/env bash", "set -euo pipefail"]
    for idx in range(check_count):
        lines.append(f'check "C{idx}" "PASS"')
        lines.append(f'check "C{idx}" "FAIL"')
    return "\n".join(lines) + "\n"


class DocsFactsGuardTest(unittest.TestCase):
    def _write_repo(self, root: Path, readme_golden_count: int, fact_golden_count: int) -> None:
        (root / "prompt-dsl-system/05_skill_registry").mkdir(parents=True, exist_ok=True)
        (root / "prompt-dsl-system/04_ai_pipeline_orchestration").mkdir(parents=True, exist_ok=True)
        (root / "prompt-dsl-system/00_conventions").mkdir(parents=True, exist_ok=True)
        (root / "prompt-dsl-system/tools").mkdir(parents=True, exist_ok=True)

        skills = [
            {"name": "skill_a", "status": "deployed", "domain": "code", "path": "a.yaml"},
            {"name": "skill_b", "status": "staging", "domain": "docs", "path": "b.yaml"},
        ]
        (root / "prompt-dsl-system/05_skill_registry/skills.json").write_text(
            json.dumps(skills, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (root / "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_a.md").write_text(
            "# P\n",
            encoding="utf-8",
        )
        (root / "prompt-dsl-system/tools/golden_path_regression.sh").write_text(
            _golden_stub(3),
            encoding="utf-8",
        )

        (root / "README.md").write_text(
            "\n".join(
                [
                    '# beyond-dev-ai-kit',
                    'subgraph "05_skill_registry (2 skills)"',
                    'subgraph "04_pipeline_orchestration (1 pipelines)"',
                    f'golden_path_regression.sh<br/>({readme_golden_count} checks)',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "prompt-dsl-system/00_conventions/FACT_BASELINE.md").write_text(
            "\n".join(
                [
                    "# FACT",
                    "- Active skills count: `2`",
                    "- Skill lifecycle distribution: `deployed=1, staging=1`",
                    "- Pipeline files (`pipeline_*.md`) count: `1`",
                    f"- `golden_path_regression.sh`: end-to-end regression ({fact_golden_count} checks: ...)",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def test_pass_when_docs_match_source_of_truth(self) -> None:
        with tempfile.TemporaryDirectory(prefix="docs-facts-pass-") as tmp:
            root = Path(tmp)
            self._write_repo(root=root, readme_golden_count=3, fact_golden_count=3)
            report = run_guard(repo_root=root)
            self.assertTrue(report["summary"]["passed"])
            self.assertEqual(report["summary"]["checks_failed"], 0)

    def test_fail_when_readme_or_fact_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="docs-facts-fail-") as tmp:
            root = Path(tmp)
            self._write_repo(root=root, readme_golden_count=2, fact_golden_count=2)
            report = run_guard(repo_root=root)
            self.assertFalse(report["summary"]["passed"])
            self.assertGreater(report["summary"]["checks_failed"], 0)
            violations = "\n".join(report.get("violations", []))
            self.assertIn("golden", violations.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)

