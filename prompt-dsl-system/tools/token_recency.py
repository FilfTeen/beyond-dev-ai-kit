#!/usr/bin/env python3
"""Check whether a risk-gate token file is freshly generated."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check token file recency")
    parser.add_argument(
        "--token-file",
        default="prompt-dsl-system/tools/RISK_GATE_TOKEN.json",
        help="Token json file path",
    )
    parser.add_argument(
        "--seconds",
        default="10",
        help="Freshness window in seconds (default: 10)",
    )
    return parser


def parse_seconds(raw: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError("seconds must be an integer")
    if value < 0:
        raise ValueError("seconds must be >= 0")
    return value


def main() -> int:
    args = build_parser().parse_args()
    try:
        window_seconds = parse_seconds(args.seconds)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    token_path = Path(args.token_file).expanduser()
    if not token_path.is_absolute():
        token_path = Path.cwd() / token_path
    token_path = token_path.resolve()

    try:
        stat = token_path.stat()
    except FileNotFoundError:
        return 1
    except OSError as exc:
        print(f"failed to stat token file: {exc}", file=sys.stderr)
        return 2

    age_seconds = max(0.0, time.time() - stat.st_mtime)
    if age_seconds <= float(window_seconds):
        print(f"FRESH_TOKEN: {token_path}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

