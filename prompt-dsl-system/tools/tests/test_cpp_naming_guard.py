#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

TEST_DIR = Path(__file__).resolve().parent
TOOLS_DIR = TEST_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from cpp_naming_guard import run_guard


class CppNamingGuardTest(unittest.TestCase):
    def test_pass_for_good_names(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpp-naming-pass-") as tmp:
            root = Path(tmp)
            src = root / "src/main/java/com/acme"
            src.mkdir(parents=True, exist_ok=True)
            (src / "Good.java").write_text(
                "\n".join(
                    [
                        "package com.acme;",
                        "public class Good {",
                        "  private static final int MAX_RETRY_COUNT = 3;",
                        "  private boolean isEnabled = true;",
                        "  private boolean hasAccess = false;",
                        "}",
                    ]
                ),
                encoding="utf-8",
            )
            report = run_guard(repo_root=root, module_root=root, mode="all")
            self.assertTrue(report["summary"]["passed"])
            self.assertEqual(report["summary"]["violations"], 0)

    def test_fail_for_bad_names(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpp-naming-fail-") as tmp:
            root = Path(tmp)
            src = root / "src/main/java/com/acme"
            src.mkdir(parents=True, exist_ok=True)
            (src / "Bad.java").write_text(
                "\n".join(
                    [
                        "package com.acme;",
                        "public class Bad {",
                        "  private static final int maxRetryCount = 3;",
                        "  private boolean enabled = true;",
                        "}",
                    ]
                ),
                encoding="utf-8",
            )
            report = run_guard(repo_root=root, module_root=root, mode="all")
            self.assertFalse(report["summary"]["passed"])
            self.assertGreaterEqual(report["summary"]["violations"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
