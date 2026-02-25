#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path
import sys

TEST_DIR = Path(__file__).resolve().parent
TOOLS_DIR = TEST_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from runtime_outputs_tracking_guard import find_runtime_tracked_outputs


class RuntimeOutputsTrackingGuardTest(unittest.TestCase):
    def test_pass_when_no_runtime_outputs_tracked(self) -> None:
        tracked = [
            "prompt-dsl-system/tools/health_reporter.py",
            "prompt-dsl-system/tools/pipeline_runner.py",
            "prompt-dsl-system/00_conventions/FACT_BASELINE.md",
        ]
        self.assertEqual(find_runtime_tracked_outputs(tracked), [])

    def test_fail_when_runtime_output_is_tracked(self) -> None:
        tracked = [
            "prompt-dsl-system/tools/health_report.json",
            "prompt-dsl-system/tools/run_plan.yaml",
            "prompt-dsl-system/tools/trace_index.json",
            "README.md",
        ]
        got = find_runtime_tracked_outputs(tracked)
        self.assertEqual(
            got,
            [
                "prompt-dsl-system/tools/health_report.json",
                "prompt-dsl-system/tools/run_plan.yaml",
                "prompt-dsl-system/tools/trace_index.json",
            ],
        )

    def test_allowlist_works_for_history_paths(self) -> None:
        tracked = ["prompt-dsl-system/tools/history/run-plans/run_plan_bugfix.yaml"]
        got = find_runtime_tracked_outputs(
            tracked,
            runtime_patterns=["prompt-dsl-system/tools/history/run-plans/*.yaml"],
            allowlist_patterns=["prompt-dsl-system/tools/history/**"],
        )
        self.assertEqual(got, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
