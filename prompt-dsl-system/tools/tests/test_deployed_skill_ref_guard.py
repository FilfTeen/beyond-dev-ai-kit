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

from deployed_skill_ref_guard import run_guard


class DeployedSkillRefGuardTest(unittest.TestCase):
    def _write_layout(self, root: Path) -> None:
        (root / "prompt-dsl-system/05_skill_registry").mkdir(parents=True, exist_ok=True)
        (root / "prompt-dsl-system/04_ai_pipeline_orchestration").mkdir(parents=True, exist_ok=True)

    def test_pass_when_all_deployed_skills_are_referenced(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deployed-ref-pass-") as tmp:
            root = Path(tmp)
            self._write_layout(root)

            (root / "prompt-dsl-system/05_skill_registry/skills.json").write_text(
                json.dumps(
                    [
                        {"name": "skill_a", "status": "deployed", "path": "a.yaml"},
                        {"name": "skill_b", "status": "deployed", "path": "b.yaml"},
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_a.md").write_text(
                "```yaml\nskill: skill_a\nparameters:\n  x: 1\n```\n",
                encoding="utf-8",
            )
            (root / "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_b.md").write_text(
                "```yaml\nskill: skill_b\nparameters:\n  x: 1\n```\n",
                encoding="utf-8",
            )

            report = run_guard(repo_root=root)
            self.assertTrue(report["summary"]["passed"])
            self.assertEqual(report["summary"]["missing_total"], 0)

    def test_fail_when_deployed_skill_has_no_pipeline_reference(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deployed-ref-fail-") as tmp:
            root = Path(tmp)
            self._write_layout(root)

            (root / "prompt-dsl-system/05_skill_registry/skills.json").write_text(
                json.dumps(
                    [
                        {"name": "skill_a", "status": "deployed", "path": "a.yaml"},
                        {"name": "skill_b", "status": "deployed", "path": "b.yaml"},
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_a.md").write_text(
                "```yaml\nskill: skill_a\nparameters:\n  x: 1\n```\n",
                encoding="utf-8",
            )

            report = run_guard(repo_root=root)
            self.assertFalse(report["summary"]["passed"])
            self.assertEqual(report["summary"]["missing_total"], 1)
            self.assertIn("skill_b", report["missing_deployed_skills"])

    def test_with_hints_reference_also_covers_base_skill(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deployed-ref-hints-alias-") as tmp:
            root = Path(tmp)
            self._write_layout(root)

            (root / "prompt-dsl-system/05_skill_registry/skills.json").write_text(
                json.dumps(
                    [
                        {"name": "skill_governance_plugin_discover", "status": "deployed", "path": "a.yaml"},
                        {
                            "name": "skill_governance_plugin_discover_with_hints",
                            "status": "deployed",
                            "path": "b.yaml",
                            "covers": ["skill_governance_plugin_discover"],
                        },
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_a.md").write_text(
                "```yaml\nskill: skill_governance_plugin_discover_with_hints\nparameters:\n  x: 1\n```\n",
                encoding="utf-8",
            )

            report = run_guard(repo_root=root)
            self.assertTrue(report["summary"]["passed"])
            self.assertEqual(report["summary"]["missing_total"], 0)

    def test_explicit_covers_metadata_supports_custom_wrapper_skill(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deployed-ref-covers-meta-") as tmp:
            root = Path(tmp)
            self._write_layout(root)

            (root / "prompt-dsl-system/05_skill_registry/skills.json").write_text(
                json.dumps(
                    [
                        {"name": "skill_core_base", "status": "deployed", "path": "a.yaml"},
                        {
                            "name": "skill_core_wrapper",
                            "status": "deployed",
                            "path": "b.yaml",
                            "covers": ["skill_core_base"],
                        },
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_a.md").write_text(
                "```yaml\nskill: skill_core_wrapper\nparameters:\n  x: 1\n```\n",
                encoding="utf-8",
            )

            report = run_guard(repo_root=root)
            self.assertTrue(report["summary"]["passed"])
            self.assertEqual(report["summary"]["missing_total"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
