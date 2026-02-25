#!/usr/bin/env python3
"""Regression checks for path_diff_guard allowlist behavior."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
TOOLS_DIR = TEST_DIR.parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from path_diff_guard import evaluate_changes, DEFAULT_GUARDRAILS


def clone_guardrails() -> dict:
    return json.loads(json.dumps(DEFAULT_GUARDRAILS))


class PathDiffGuardTest(unittest.TestCase):
    def test_governance_docs_allowed_for_prompt_dsl_module(self) -> None:
        changed_files = ["AGENTS.md", "AGENTS.zh-CN.md", "README.md", "README.zh-CN.md"]
        _, violations, _, _ = evaluate_changes(changed_files, "prompt-dsl-system", clone_guardrails())
        self.assertEqual(violations, [])

    def test_non_governance_root_file_still_blocked(self) -> None:
        changed_files = ["SECURITY.md"]
        _, violations, _, _ = evaluate_changes(changed_files, "prompt-dsl-system", clone_guardrails())
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].get("rule"), "out_of_allowed_scope")

    def test_packaging_allowlist_without_module_path(self) -> None:
        changed_files = ["README.md"]
        _, violations, _, _ = evaluate_changes(changed_files, None, clone_guardrails())
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
