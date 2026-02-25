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

from fact_baseline_refresh import refresh_fact_baseline


FACT_MIN_TEMPLATE = """# FACT BASELINE (prompt-dsl-system)

Generated at: 2026-02-01 (local)
Scope: `prompt-dsl-system/**`

## 1) Current Skills Baseline

- Active registry file: `prompt-dsl-system/05_skill_registry/skills.json`
- Active skills count: `6`
- Domain distribution: `universal=1, governance=5`

## 2) Current Pipelines Baseline

- Pipeline files (`pipeline_*.md`) count: `13`

## 3) Current Tools Boundary

- `kit_selfcheck.py`: outputs toolkit quality scorecards (`kit_selfcheck_report.json` + `.md`) across 7 dimensions with missing-path recommendations
"""


class FactBaselineRefreshTest(unittest.TestCase):
    def test_refresh_updates_key_lines(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fact-refresh-") as tmp:
            root = Path(tmp)
            (root / "prompt-dsl-system/00_conventions").mkdir(parents=True, exist_ok=True)
            (root / "prompt-dsl-system/05_skill_registry").mkdir(parents=True, exist_ok=True)
            (root / "prompt-dsl-system/04_ai_pipeline_orchestration").mkdir(parents=True, exist_ok=True)

            fact_path = root / "prompt-dsl-system/00_conventions/FACT_BASELINE.md"
            fact_path.write_text(FACT_MIN_TEMPLATE, encoding="utf-8")

            skills = [
                {"name": "skill_a", "domain": "governance", "status": "deployed", "path": "a.yaml"},
                {"name": "skill_b", "domain": "test", "status": "staging", "path": "b.yaml"},
            ]
            (root / "prompt-dsl-system/05_skill_registry/skills.json").write_text(
                json.dumps(skills, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_a.md").write_text(
                "# Pipeline A\n",
                encoding="utf-8",
            )
            (root / "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_b.md").write_text(
                "# Pipeline B\n",
                encoding="utf-8",
            )

            report = refresh_fact_baseline(repo_root=root, fact_path=fact_path)
            self.assertEqual(report["skills_total"], 2)
            self.assertEqual(report["pipelines_total"], 2)

            text = fact_path.read_text(encoding="utf-8")
            self.assertIn("- Active skills count: `2`", text)
            self.assertIn("- Pipeline files (`pipeline_*.md`) count: `2`", text)
            self.assertIn("Skill lifecycle distribution", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
