#!/usr/bin/env python3
"""merged_guard.py

Validate merged/batches integrity for a trace delivery package.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

EXPECTED_SEGMENTS = [
    "01_drop_tables.sql",
    "02_create_public_notice.sql",
    "03_create_public_notice_scope.sql",
    "04_create_public_notice_cover.sql",
    "05_create_public_notice_external_source.sql",
    "07_create_public_notice_read.sql",
    "06_create_index.sql",
    "08_upgrade_from_legacy.sql",
    "10_menu_and_role_config.sql",
]

CORE_TABLES = [
    "PUBLIC_NOTICE",
    "PUBLIC_NOTICE_SCOPE",
    "PUBLIC_NOTICE_COVER",
    "PUBLIC_NOTICE_EXTERNAL_SOURCE",
    "PUBLIC_NOTICE_READ",
]

SEGMENT_PATTERN = re.compile(r"^\s*--\s*>>>\s*FILE:\s*([^\s]+)\s*$", re.MULTILINE)


def extract_segments(content: str) -> List[str]:
    return SEGMENT_PATTERN.findall(content)


def has_create_table(content: str, table_name: str) -> bool:
    pattern = re.compile(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:[A-Z0-9_]+\.)?{re.escape(table_name)}\b",
        re.IGNORECASE,
    )
    return bool(pattern.search(content))


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate merged SQL integrity for a trace delivery package."
    )
    parser.add_argument(
        "--trace-id",
        required=True,
        help="Trace id under prompt-dsl-system/tools/deliveries/<trace_id>/",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    tools_dir = Path(__file__).resolve().parent
    trace_dir = tools_dir / "deliveries" / args.trace_id

    batch_all_rel = Path("batches/Batch_all_merged.sql")
    merged_rel = Path("step2/A1_dm8_sql_merged.sql")
    batch2_rel = Path("batches/Batch2_core_schema.sql")
    manifest_rel = Path("batches/BATCH_manifest.md")

    files = {
        "Batch_all_merged.sql": trace_dir / batch_all_rel,
        "A1_dm8_sql_merged.sql": trace_dir / merged_rel,
        "Batch2_core_schema.sql": trace_dir / batch2_rel,
        "BATCH_manifest.md": trace_dir / manifest_rel,
    }

    report: Dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trace_id": args.trace_id,
        "pass": True,
        "missing_segments": {},
        "missing_tables": {},
        "suggested_actions": [],
        "checks": {},
    }

    checks: Dict[str, object] = {}

    missing_required_files = []
    for required_name in ["Batch_all_merged.sql", "A1_dm8_sql_merged.sql", "Batch2_core_schema.sql"]:
        if not files[required_name].is_file():
            missing_required_files.append(required_name)

    checks["required_files"] = {
        "pass": len(missing_required_files) == 0,
        "missing_files": missing_required_files,
    }

    manifest_exists = files["BATCH_manifest.md"].is_file()
    checks["optional_manifest"] = {
        "present": manifest_exists,
    }

    merged_targets = ["Batch_all_merged.sql", "A1_dm8_sql_merged.sql"]
    for target_name in merged_targets:
        path = files[target_name]
        target_result: Dict[str, object] = {
            "present": path.is_file(),
            "segment_count_ok": False,
            "segment_order_ok": False,
            "contains_public_notice_read_create": False,
            "segments_found": [],
            "extra_segments": [],
            "missing_segments": [],
        }

        if path.is_file():
            content = load_text(path)
            segments = extract_segments(content)
            target_result["segments_found"] = segments
            target_result["segment_count_ok"] = len(segments) == len(EXPECTED_SEGMENTS)
            target_result["segment_order_ok"] = segments == EXPECTED_SEGMENTS
            target_result["extra_segments"] = [s for s in segments if s not in EXPECTED_SEGMENTS]
            missing = [s for s in EXPECTED_SEGMENTS if s not in segments]
            target_result["missing_segments"] = missing
            if missing:
                report["missing_segments"][target_name] = missing

            has_pnr = has_create_table(content, "PUBLIC_NOTICE_READ")
            target_result["contains_public_notice_read_create"] = has_pnr
            if not has_pnr:
                report["missing_tables"][target_name] = ["PUBLIC_NOTICE_READ"]

        checks[target_name] = target_result

    batch2_result: Dict[str, object] = {
        "present": files["Batch2_core_schema.sql"].is_file(),
        "missing_tables": [],
        "pass": False,
    }
    if files["Batch2_core_schema.sql"].is_file():
        batch2_content = load_text(files["Batch2_core_schema.sql"])
        missing_core_tables = [
            table_name for table_name in CORE_TABLES if not has_create_table(batch2_content, table_name)
        ]
        batch2_result["missing_tables"] = missing_core_tables
        batch2_result["pass"] = len(missing_core_tables) == 0
        if missing_core_tables:
            report["missing_tables"]["Batch2_core_schema.sql"] = missing_core_tables
    checks["Batch2_core_schema.sql"] = batch2_result

    report["checks"] = checks

    fail_conditions = []
    if missing_required_files:
        fail_conditions.append("missing_required_files")

    for target_name in merged_targets:
        tr = checks[target_name]
        if not tr["present"]:
            continue
        if not tr["segment_count_ok"]:
            fail_conditions.append(f"{target_name}:segment_count")
        if not tr["segment_order_ok"]:
            fail_conditions.append(f"{target_name}:segment_order")
        if not tr["contains_public_notice_read_create"]:
            fail_conditions.append(f"{target_name}:public_notice_read_create")

    if not batch2_result["pass"]:
        fail_conditions.append("Batch2_core_schema.sql:missing_core_tables")

    report["pass"] = len(fail_conditions) == 0
    report["fail_reasons"] = fail_conditions

    actions: List[str] = []
    if missing_required_files:
        actions.append("补齐缺失文件后重试校验。")
    segment_issues = [r for r in fail_conditions if "segment_count" in r or "segment_order" in r]
    if segment_issues:
        actions.append("重新生成 merged（Batch_all_merged.sql 与 step2/A1_dm8_sql_merged.sql），确保 9 段且顺序一致。")
    if any("public_notice_read_create" in r for r in fail_conditions):
        actions.append("在 merged 脚本中补齐 CREATE TABLE PUBLIC_NOTICE_READ 段（通常来自 07_create_public_notice_read.sql）。")
    if any("Batch2_core_schema.sql:missing_core_tables" == r for r in fail_conditions):
        actions.append("重建 Batch2_core_schema.sql，确保 5 张核心表 CREATE TABLE 全部纳入。")
    if not actions:
        actions.append("无需动作。")

    report["suggested_actions"] = actions

    report_path = tools_dir / "merged_integrity_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if report["pass"]:
        print("PASS merged integrity check")
        print("report: merged_integrity_report.json")
        return 0

    print("FAIL merged integrity check")
    print("report: merged_integrity_report.json")
    for reason in fail_conditions:
        print(f"- {reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
