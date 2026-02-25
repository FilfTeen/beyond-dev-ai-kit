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

from skill_promotion_matrix import build_report


SKILL_YAML_TEMPLATE = """name: "{name}"
description: "desc"
parameters:
  - name: "module_path"
    type: "string"
prompt_template: |
  prompt
output_contract:
  summary: "string"
examples:
  - input:
      module_path: "/x"
"""


class SkillPromotionMatrixTest(unittest.TestCase):
    def _write_repo_layout(self, root: Path) -> None:
        (root / "prompt-dsl-system/05_skill_registry/skills/code").mkdir(parents=True, exist_ok=True)
        (root / "prompt-dsl-system/04_ai_pipeline_orchestration").mkdir(parents=True, exist_ok=True)

    def test_ready_when_skill_is_referenced_by_pipeline(self) -> None:
        with tempfile.TemporaryDirectory(prefix="promotion-ready-") as tmp:
            root = Path(tmp)
            self._write_repo_layout(root)

            skill_path = "prompt-dsl-system/05_skill_registry/skills/code/skill_demo_ready.yaml"
            (root / skill_path).write_text(SKILL_YAML_TEMPLATE.format(name="skill_demo_ready"), encoding="utf-8")

            skills = [
                {
                    "name": "skill_demo_ready",
                    "domain": "code",
                    "path": skill_path,
                    "status": "staging",
                }
            ]
            (root / "prompt-dsl-system/05_skill_registry/skills.json").write_text(
                json.dumps(skills, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_demo.md").write_text(
                "## Step\n```yaml\nskill: skill_demo_ready\nparameters:\n  module_path: x\n```\n",
                encoding="utf-8",
            )

            report = build_report(repo_root=root)
            self.assertEqual(report["summary"]["staging_total"], 1)
            self.assertEqual(report["summary"]["ready_total"], 1)
            self.assertEqual(report["summary"]["pending_total"], 0)
            self.assertTrue(report["items"][0]["ready"])

    def test_pending_when_skill_not_referenced_by_pipeline(self) -> None:
        with tempfile.TemporaryDirectory(prefix="promotion-pending-") as tmp:
            root = Path(tmp)
            self._write_repo_layout(root)

            skill_path = "prompt-dsl-system/05_skill_registry/skills/code/skill_demo_pending.yaml"
            (root / skill_path).write_text(SKILL_YAML_TEMPLATE.format(name="skill_demo_pending"), encoding="utf-8")

            skills = [
                {
                    "name": "skill_demo_pending",
                    "domain": "code",
                    "path": skill_path,
                    "status": "staging",
                }
            ]
            (root / "prompt-dsl-system/05_skill_registry/skills.json").write_text(
                json.dumps(skills, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_other.md").write_text(
                "## Step\n```yaml\nskill: skill_other\nparameters:\n  module_path: x\n```\n",
                encoding="utf-8",
            )

            report = build_report(repo_root=root)
            self.assertEqual(report["summary"]["staging_total"], 1)
            self.assertEqual(report["summary"]["ready_total"], 0)
            self.assertEqual(report["summary"]["pending_total"], 1)
            self.assertFalse(report["items"][0]["ready"])
            self.assertIn("referenced_by_pipeline", report["items"][0]["missing"])

    def test_skill_name_in_objective_text_is_not_counted_as_reference(self) -> None:
        with tempfile.TemporaryDirectory(prefix="promotion-false-positive-") as tmp:
            root = Path(tmp)
            self._write_repo_layout(root)

            skill_path = "prompt-dsl-system/05_skill_registry/skills/code/skill_demo_text_only.yaml"
            (root / skill_path).write_text(SKILL_YAML_TEMPLATE.format(name="skill_demo_text_only"), encoding="utf-8")

            skills = [
                {
                    "name": "skill_demo_text_only",
                    "domain": "code",
                    "path": skill_path,
                    "status": "staging",
                }
            ]
            (root / "prompt-dsl-system/05_skill_registry/skills.json").write_text(
                json.dumps(skills, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_text_only.md").write_text(
                "## Step\n```yaml\nskill: skill_other\nparameters:\n  objective: \"refs_hint: skill_demo_text_only\"\n```\n",
                encoding="utf-8",
            )

            report = build_report(repo_root=root)
            self.assertEqual(report["summary"]["pending_total"], 1)
            self.assertFalse(report["items"][0]["ready"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
