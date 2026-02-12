#!/usr/bin/env python3
"""Inject post-validate gate summary into health_report JSON/Markdown."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_JSON = "prompt-dsl-system/tools/health_report.json"
DEFAULT_MD = "prompt-dsl-system/tools/health_report.md"
START_MARKER = "<!-- POST_VALIDATE_GATES_START -->"
END_MARKER = "<!-- POST_VALIDATE_GATES_END -->"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_gate(raw: str) -> Dict[str, Any]:
    parts = [p.strip() for p in str(raw or "").split(":", 2)]
    if len(parts) != 3:
        raise ValueError(f"invalid gate format: {raw}")
    name, status, rc_text = parts
    if not name:
        raise ValueError(f"invalid gate name: {raw}")
    status_norm = status.upper() if status else "UNKNOWN"
    try:
        rc = int(rc_text)
    except ValueError:
        rc = -1
    return {"name": name, "status": status_norm, "exit_code": rc}


def overall_status(gates: List[Dict[str, Any]]) -> str:
    for item in gates:
        if str(item.get("status", "")).upper() == "FAIL":
            return "FAIL"
    return "PASS"


def load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def render_block(section: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(START_MARKER)
    lines.append("## Post-Validate Gates")
    lines.append(f"- Overall: {section.get('overall_status', 'UNKNOWN')}")
    lines.append(f"- Updated: {section.get('generated_at', '-')}")
    lines.append("")
    lines.append("| Gate | Status | Exit |")
    lines.append("|---|---|---:|")
    gates = section.get("gates", [])
    if isinstance(gates, list) and gates:
        for gate in gates:
            lines.append(
                f"| {gate.get('name', '-')} | {gate.get('status', 'UNKNOWN')} | {gate.get('exit_code', -1)} |"
            )
    else:
        lines.append("| none | UNKNOWN | -1 |")
    lines.append(END_MARKER)
    return "\n".join(lines)


def upsert_md(md_path: Path, section: Dict[str, Any]) -> None:
    block = render_block(section)
    if md_path.is_file():
        raw = md_path.read_text(encoding="utf-8", errors="ignore")
    else:
        raw = "# Health Report\n"

    start = raw.find(START_MARKER)
    end = raw.find(END_MARKER)
    if start >= 0 and end >= 0 and end >= start:
        end_pos = end + len(END_MARKER)
        if end_pos < len(raw) and raw[end_pos:end_pos + 1] == "\n":
            end_pos += 1
        merged = raw[:start].rstrip() + "\n\n" + block + "\n"
    else:
        merged = raw.rstrip() + "\n\n" + block + "\n"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(merged, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync post-validate gate result into health report")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--report-json", default=DEFAULT_JSON)
    parser.add_argument("--report-md", default=DEFAULT_MD)
    parser.add_argument("--gate", action="append", default=[], help="name:status:exit_code")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[post_validate_sync] FAIL: invalid repo-root: {repo_root}")
        return 2

    gates: List[Dict[str, Any]] = []
    for item in args.gate:
        gates.append(parse_gate(item))

    section = {
        "generated_at": now_iso(),
        "overall_status": overall_status(gates),
        "gates": gates,
    }

    report_json = Path(args.report_json)
    report_md = Path(args.report_md)
    if not report_json.is_absolute():
        report_json = repo_root / report_json
    if not report_md.is_absolute():
        report_md = repo_root / report_md

    payload = load_json(report_json)
    payload["post_validate_gates"] = section
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upsert_md(report_md, section)

    print(f"[post_validate_sync] PASS: {report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
