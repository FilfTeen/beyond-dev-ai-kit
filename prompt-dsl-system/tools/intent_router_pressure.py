#!/usr/bin/env python3
"""Compatibility wrapper for intent_router pressure checks.

Canonical script now lives under:
prompt-dsl-system/tools/tests/intent_router/intent_router_pressure.py
"""

from __future__ import annotations

import runpy
from pathlib import Path

IMPL_FILE = (
    Path(__file__).resolve().parent
    / "tests"
    / "intent_router"
    / "intent_router_pressure.py"
)
IMPL_GLOBALS = runpy.run_path(str(IMPL_FILE))
main = IMPL_GLOBALS["main"]


if __name__ == "__main__":
    raise SystemExit(main())
