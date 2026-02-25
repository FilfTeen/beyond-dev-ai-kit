#!/usr/bin/env python3
"""Regression checks for agent_capability_audit."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
TOOLS_DIR = TEST_DIR.parent.parent
REPO_ROOT = TOOLS_DIR.parent.parent
AUDIT_SCRIPT = TOOLS_DIR / "agent_capability_audit.py"


def run_audit(args: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(AUDIT_SCRIPT)] + args
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


class AgentCapabilityAuditTest(unittest.TestCase):
    def test_skip_pressure_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent-cap-audit-") as tmp:
            out_json = Path(tmp) / "audit.json"
            out_md = Path(tmp) / "audit.md"
            proc = run_audit(
                [
                    "--repo-root",
                    str(REPO_ROOT),
                    "--skip-pressure",
                    "--out-json",
                    str(out_json),
                    "--out-md",
                    str(out_md),
                ]
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            self.assertTrue(out_json.is_file())
            self.assertTrue(out_md.is_file())
            payload = json.loads(out_json.read_text(encoding="utf-8"))

            summary = payload.get("summary", {})
            self.assertIn("overall_score", summary)
            self.assertIn("overall_level", summary)
            self.assertEqual(int(payload.get("coverage", {}).get("summary", {}).get("dimension_count", 0)), 3)
            self.assertEqual(int(payload.get("route_probes", {}).get("passed_count", 0)), 3)
            self.assertEqual(int(payload.get("route_probes", {}).get("total", 0)), 3)

    def test_pressure_gate_smoke(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent-cap-audit-gate-") as tmp:
            out_json = Path(tmp) / "audit.json"
            out_md = Path(tmp) / "audit.md"
            proc = run_audit(
                [
                    "--repo-root",
                    str(REPO_ROOT),
                    "--single-calls",
                    "400",
                    "--concurrent-calls",
                    "800",
                    "--concurrency",
                    "8",
                    "--max-p99-ms",
                    "20",
                    "--min-overall-score",
                    "0.80",
                    "--min-overall-level",
                    "medium",
                    "--require-pressure-pass",
                    "true",
                    "--out-json",
                    str(out_json),
                    "--out-md",
                    str(out_md),
                ]
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(int(payload.get("pressure_test", {}).get("returncode", -1)), 0)
            self.assertGreaterEqual(float(payload.get("summary", {}).get("overall_score", 0.0)), 0.8)

    def test_gate_failure_when_pressure_required_but_skipped(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent-cap-audit-fail-") as tmp:
            out_json = Path(tmp) / "audit.json"
            out_md = Path(tmp) / "audit.md"
            proc = run_audit(
                [
                    "--repo-root",
                    str(REPO_ROOT),
                    "--skip-pressure",
                    "--min-overall-score",
                    "0.80",
                    "--min-overall-level",
                    "medium",
                    "--require-pressure-pass",
                    "true",
                    "--out-json",
                    str(out_json),
                    "--out-md",
                    str(out_md),
                ]
            )
            self.assertEqual(proc.returncode, 52, msg=proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
