"""Unit tests for pipeline_profile_injector module."""

import sys
import os
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pipeline_profile_injector import (
    load_company_profile,
    profile_effective_defaults,
    detect_target_db,
    choose_profile_execution_tool,
    inject_profile_defaults,
)


class TestLoadCompanyProfile(unittest.TestCase):
    def test_missing_file(self):
        profile, warnings = load_company_profile(Path("/nonexistent/path.yaml"))
        self.assertIsNone(profile)
        self.assertTrue(any("not found" in w for w in warnings))

    def test_valid_profile(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("db_execution:\n  default_schema_strategy: create_if_absent\n")
            f.flush()
            profile, warnings = load_company_profile(Path(f.name))
        os.unlink(f.name)
        self.assertIsNotNone(profile)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(
            profile["db_execution"]["default_schema_strategy"], "create_if_absent"
        )


class TestProfileEffectiveDefaults(unittest.TestCase):
    def test_none_profile(self):
        self.assertEqual(profile_effective_defaults(None), {})

    def test_no_db_execution(self):
        self.assertEqual(profile_effective_defaults({"other": "x"}), {})

    def test_schema_strategy(self):
        profile = {"db_execution": {"default_schema_strategy": "create_if_absent"}}
        defaults = profile_effective_defaults(profile)
        self.assertEqual(defaults["schema_strategy"], "create_if_absent")

    def test_dm_tool(self):
        profile = {"db_execution": {"preferred_dm_tool": "DBeaver"}}
        defaults = profile_effective_defaults(profile)
        self.assertEqual(defaults["execution_tool"], "DBeaver")


class TestDetectTargetDb(unittest.TestCase):
    def test_explicit_oracle(self):
        self.assertEqual(detect_target_db({"target_db": "Oracle"}), "oracle")

    def test_explicit_dm(self):
        self.assertEqual(detect_target_db({"target_db": "dm8"}), "dm8")

    def test_from_objective_oracle(self):
        self.assertEqual(detect_target_db({"objective": "migrate to Oracle"}), "oracle")

    def test_default_dm8(self):
        self.assertEqual(detect_target_db({}), "dm8")

    def test_empty_target_db(self):
        self.assertEqual(detect_target_db({"target_db": ""}), "dm8")


class TestChooseProfileExecutionTool(unittest.TestCase):
    def test_none_profile(self):
        self.assertIsNone(choose_profile_execution_tool(None, "dm8"))

    def test_dm_preferred(self):
        profile = {"db_execution": {"preferred_dm_tool": "DBeaver"}}
        self.assertEqual(choose_profile_execution_tool(profile, "dm8"), "DBeaver")

    def test_oracle_preferred(self):
        profile = {"db_execution": {"preferred_oracle_tool": "SQLPlus"}}
        self.assertEqual(choose_profile_execution_tool(profile, "oracle"), "SQLPlus")

    def test_fallback_to_dm(self):
        profile = {"db_execution": {"preferred_dm_tool": "DBeaver"}}
        self.assertEqual(choose_profile_execution_tool(profile, "oracle"), "DBeaver")


class TestInjectProfileDefaults(unittest.TestCase):
    def test_none_profile(self):
        params = {"mode": "scan"}
        updated, injected = inject_profile_defaults(params, None)
        self.assertEqual(updated, params)
        self.assertEqual(injected, {})

    def test_additive_only(self):
        """Existing params should NOT be overwritten."""
        profile = {"db_execution": {"default_schema_strategy": "drop_create"}}
        params = {"schema_strategy": "keep_existing"}
        updated, injected = inject_profile_defaults(params, profile)
        self.assertEqual(updated["schema_strategy"], "keep_existing")
        self.assertNotIn("schema_strategy", injected)

    def test_injects_missing_defaults(self):
        profile = {
            "db_execution": {
                "default_schema_strategy": "create_if_absent",
                "preferred_dm_tool": "DBeaver",
            }
        }
        params = {"mode": "scan"}
        updated, injected = inject_profile_defaults(params, profile)
        self.assertEqual(updated["schema_strategy"], "create_if_absent")
        self.assertEqual(updated["execution_tool"], "DBeaver")
        self.assertIn("schema_strategy", injected)
        self.assertIn("execution_tool", injected)


if __name__ == "__main__":
    unittest.main()
