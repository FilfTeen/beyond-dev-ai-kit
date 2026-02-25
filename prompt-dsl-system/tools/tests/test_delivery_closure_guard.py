#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

TEST_DIR = Path(__file__).resolve().parent
TOOLS_DIR = TEST_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from delivery_closure_guard import run_guard


class DeliveryClosureGuardTest(unittest.TestCase):
    def _create_min_repo(self, root: Path) -> None:
        (root / "prompt-dsl-system/tools/artifacts/templates/kit_self_upgrade").mkdir(
            parents=True, exist_ok=True
        )
        (root / "README.md").write_text("# repo\n", encoding="utf-8")
        (root / "EVOLUTION_LOG.md").write_text("# evolution log\n", encoding="utf-8")
        (root / "CHANGELOG.md").write_text("# changelog\n", encoding="utf-8")

        (root / "prompt-dsl-system/tools/artifacts/templates/kit_self_upgrade/A3_change_ledger.template.md").write_text(
            "## File Changes\n",
            encoding="utf-8",
        )
        (root / "prompt-dsl-system/tools/artifacts/templates/kit_self_upgrade/A3_rollback_plan.template.md").write_text(
            "## Rollback Trigger\n",
            encoding="utf-8",
        )
        (root / "prompt-dsl-system/tools/artifacts/templates/kit_self_upgrade/A3_cleanup_report.template.md").write_text(
            "## Final Status\n",
            encoding="utf-8",
        )

    def test_pass_when_docs_templates_and_no_dirty_noise(self) -> None:
        with tempfile.TemporaryDirectory(prefix="delivery-closure-pass-") as tmp:
            root = Path(tmp)
            self._create_min_repo(root)
            with patch("delivery_closure_guard.git_changed_paths", return_value=[]):
                report = run_guard(repo_root=root)
            self.assertTrue(report["summary"]["passed"])
            self.assertEqual(report["summary"]["checks_failed"], 0)

    def test_fail_when_code_changed_without_doc_update_and_temp_noise(self) -> None:
        with tempfile.TemporaryDirectory(prefix="delivery-closure-fail-") as tmp:
            root = Path(tmp)
            self._create_min_repo(root)
            changed = [
                "prompt-dsl-system/tools/run.sh",
                "tmp/.tmp",
            ]
            with patch("delivery_closure_guard.git_changed_paths", return_value=changed):
                report = run_guard(repo_root=root)
            self.assertFalse(report["summary"]["passed"])
            checks = {
                item["name"]: bool(item["passed"])
                for item in report["checks"]
                if isinstance(item, dict)
            }
            self.assertFalse(checks.get("closure_docs_updated_when_code_changed", True))
            self.assertFalse(checks.get("no_temp_noise_in_workspace", True))


if __name__ == "__main__":
    unittest.main(verbosity=2)

