#!/usr/bin/env python3
"""Append optional ACK rationale notes (jsonl) for audit trail."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_int(value: Any) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return 0
    return n


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Append ACK rationale note to jsonl")
    p.add_argument("--repo-root", required=True)
    p.add_argument("--command", required=True)
    p.add_argument("--context-id", required=True)
    p.add_argument("--trace-id", required=True)
    p.add_argument("--note", required=True)
    p.add_argument("--verify-hits-total", default="")
    p.add_argument("--output", default="prompt-dsl-system/tools/ack_notes.jsonl")
    return p


def main() -> int:
    args = build_parser().parse_args()

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        print(f"Invalid repo root: {repo_root}")
        return 2

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (repo_root / output_path).resolve()

    note = str(args.note or "").strip()
    if not note:
        print("--note is required")
        return 2

    verify_hits_total = parse_int(args.verify_hits_total)

    payload: Dict[str, Any] = {
        "timestamp": now_iso(),
        "repo_root": str(repo_root),
        "command": str(args.command).strip(),
        "context_id": str(args.context_id).strip(),
        "trace_id": str(args.trace_id).strip(),
        "note": note,
        "verify_hits_total": verify_hits_total,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    print(f"ack_note_written: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
