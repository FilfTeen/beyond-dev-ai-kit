#!/usr/bin/env python3
"""Compatibility wrapper for intent_router regression tests.

Canonical tests now live under:
prompt-dsl-system/tools/tests/intent_router/test_intent_router.py
"""

from __future__ import annotations

import runpy
import unittest
from pathlib import Path

IMPL_FILE = (
    Path(__file__).resolve().parent
    / "tests"
    / "intent_router"
    / "test_intent_router.py"
)
IMPL_GLOBALS = runpy.run_path(str(IMPL_FILE))
IntentRouterTest = IMPL_GLOBALS["IntentRouterTest"]


if __name__ == "__main__":
    unittest.main(verbosity=2)
