#!/usr/bin/env python3
"""Regression and lightweight performance checks for intent_router."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from intent_router import choose_action, infer_module_path


CASE_FILE = TOOLS_DIR / "testdata" / "intent_router_cases.json"


class IntentRouterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = CASE_FILE.read_text(encoding="utf-8")
        cls.cases = json.loads(raw)

    def test_regression_cases(self) -> None:
        for case in self.cases:
            goal = str(case["goal"])
            expect_action_kind = str(case["expect_action_kind"])
            expect_target_suffix = str(case["expect_target_suffix"])
            min_conf = float(case.get("min_confidence", 0.0))
            expect_default_module_path = case.get("expect_default_module_path", "__absent__")
            with self.subTest(goal=goal, expect=expect_target_suffix):
                routed = choose_action(goal, TOOLS_DIR.parent.parent)
                selected = routed["selected"]
                self.assertEqual(selected["action_kind"], expect_action_kind)
                self.assertTrue(str(selected["target"]).endswith(expect_target_suffix))
                self.assertGreaterEqual(float(selected["confidence"]), min_conf)
                if expect_default_module_path != "__absent__":
                    self.assertEqual(selected.get("default_module_path"), expect_default_module_path)

    def test_module_path_boundary_gating(self) -> None:
        router_path = TOOLS_DIR / "intent_router.py"
        repo_root = TOOLS_DIR.parent.parent

        business_goal = "请执行 pipeline_ownercommittee_audit_fix.md 并给出计划"
        proc_business = subprocess.run(
            [sys.executable, str(router_path), "--repo-root", str(repo_root), "--goal", business_goal],
            check=True,
            text=True,
            capture_output=True,
        )
        routed_business = json.loads(proc_business.stdout)
        self.assertEqual(routed_business["module_path_source"], "missing")
        self.assertFalse(bool(routed_business["execution_ready"]))
        self.assertFalse(bool(routed_business["can_auto_execute"]))

        gov_goal = "请执行 pipeline_skill_creator.md 并给出计划"
        proc_gov = subprocess.run(
            [sys.executable, str(router_path), "--repo-root", str(repo_root), "--goal", gov_goal],
            check=True,
            text=True,
            capture_output=True,
        )
        routed_gov = json.loads(proc_gov.stdout)
        self.assertEqual(routed_gov["module_path_source"], "selected_default")
        self.assertTrue(bool(routed_gov["execution_ready"]))
        self.assertTrue(bool(routed_gov["can_auto_execute"]))

    def test_route_latency_budget(self) -> None:
        goals = [str(case["goal"]) for case in self.cases]
        loops = 120
        started = time.perf_counter()
        for _ in range(loops):
            for goal in goals:
                choose_action(goal, TOOLS_DIR.parent.parent)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        avg_ms = elapsed_ms / float(loops * len(goals))
        # Keep this threshold relaxed across different developer machines.
        self.assertLess(avg_ms, 5.0)

    def test_infer_module_path_sanitization(self) -> None:
        cases = [
            ('修复问题 module_path="/tmp/a/b"', "/tmp/a/b"),
            ("修复问题 module_path='/tmp/a/b'", "/tmp/a/b"),
            ("修复问题 /tmp/a/b。并验证", "/tmp/a/b"),
            ("修复问题 ./module/a); 并验证", "./module/a"),
            ("修复问题 ../module/a】 并验证", "../module/a"),
        ]
        for goal, expected in cases:
            with self.subTest(goal=goal):
                self.assertEqual(infer_module_path(goal), expected)

    def test_execute_scope_precheck_blocks_out_of_scope_dirty_workspace(self) -> None:
        router_path = TOOLS_DIR / "intent_router.py"
        with tempfile.TemporaryDirectory(prefix="intent-router-scope-") as tmp:
            root = Path(tmp)
            (root / "prompt-dsl-system/04_ai_pipeline_orchestration").mkdir(parents=True, exist_ok=True)
            (root / "prompt-dsl-system/tools").mkdir(parents=True, exist_ok=True)
            (root / "README.md").write_text("# temp\n", encoding="utf-8")
            (root / "prompt-dsl-system/tools/run.sh").write_text("#!/usr/bin/env bash\necho noop\n", encoding="utf-8")
            pipeline = root / "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_skill_creator.md"
            pipeline.write_text(
                "# Pipeline: Skill Creator\\n\\n## 适用场景\\n- `allowed_module_root`：必须为 `prompt-dsl-system`。\\n",
                encoding="utf-8",
            )

            subprocess.run(["git", "init"], cwd=str(root), check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=str(root), check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=bot", "-c", "user.email=bot@example.com", "commit", "-m", "init"],
                cwd=str(root),
                check=True,
                capture_output=True,
                text=True,
            )

            # Make an out-of-scope dirty change.
            (root / "README.md").write_text("# dirty\n", encoding="utf-8")

            proc = subprocess.run(
                [
                    sys.executable,
                    str(router_path),
                    "--repo-root",
                    str(root),
                    "--goal",
                    "请执行 pipeline_skill_creator.md 并给出计划",
                    "--execute",
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 2)
            routed = json.loads(proc.stdout)
            blockers = routed.get("execution_blockers", [])
            self.assertIn("workspace_out_of_scope_changes", blockers)
            scope_check = routed.get("workspace_scope_check", {})
            self.assertGreaterEqual(int(scope_check.get("out_of_scope_count", 0)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
