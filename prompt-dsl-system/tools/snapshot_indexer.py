#!/usr/bin/env python3
"""Build snapshot index for tools/snapshots."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from policy_loader import build_cli_override_dict, get_policy_value, load_policy

MB = 1024 * 1024


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_cli_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def parse_int(value: Any, default: int, minimum: int = 0) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if n < minimum:
        return minimum
    return n


def parse_iso8601(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def to_path(raw: str, base: Path) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = (base / p).resolve()
    else:
        p = p.resolve()
    return p


def to_mb(size_bytes: int) -> float:
    return round(float(size_bytes) / float(MB), 3)


def calc_dir_size(snapshot_dir: Path) -> Tuple[int, List[str]]:
    warnings: List[str] = []
    total = 0
    for root, dirs, files in os.walk(snapshot_dir, topdown=True, followlinks=False):
        root_path = Path(root)
        kept_dirs: List[str] = []
        for d in dirs:
            dp = root_path / d
            if dp.is_symlink():
                warnings.append(f"skip_symlink_dir:{dp}")
                continue
            kept_dirs.append(d)
        dirs[:] = kept_dirs

        for f in files:
            fp = root_path / f
            if fp.is_symlink():
                warnings.append(f"skip_symlink_file:{fp}")
                continue
            try:
                total += fp.stat().st_size
            except OSError:
                warnings.append(f"stat_failed:{fp}")
    return total, warnings


def discover_snapshots(snapshots_dir: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    valid: List[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []

    if not snapshots_dir.exists() or not snapshots_dir.is_dir():
        return valid, invalid

    for entry in sorted(snapshots_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            invalid.append({"path": str(entry.resolve()), "reason": "not_directory"})
            continue
        if not entry.name.startswith("snapshot_"):
            invalid.append({"path": str(entry.resolve()), "reason": "name_not_snapshot_prefix"})
            continue

        manifest_path = (entry / "manifest.json").resolve()
        if not manifest_path.exists() or not manifest_path.is_file():
            invalid.append({"path": str(entry.resolve()), "reason": "missing_manifest_json"})
            continue

        manifest = safe_read_json(manifest_path)
        if not manifest:
            invalid.append({"path": str(entry.resolve()), "reason": "manifest_parse_failed"})
            continue

        created_raw = manifest.get("created_at")
        created_dt = parse_iso8601(str(created_raw) if created_raw is not None else "")
        if created_dt is None:
            invalid.append({"path": str(entry.resolve()), "reason": "invalid_created_at"})
            continue

        size_bytes, warnings = calc_dir_size(entry)

        item = {
            "snapshot_id": str(manifest.get("snapshot_id") or entry.name),
            "path": str(entry.resolve()),
            "created_at": created_dt.isoformat(),
            "created_at_dt": created_dt,
            "label": str(manifest.get("label") or ""),
            "trace_id": str(manifest.get("trace_id") or ""),
            "context_id": str(manifest.get("context_id") or ""),
            "repo_root": str(manifest.get("repo_root") or ""),
            "size_bytes": int(size_bytes),
            "size_mb": to_mb(size_bytes),
            "warnings": warnings,
        }
        valid.append(item)

    return valid, invalid


def build_md(
    generated_at: str,
    snapshots_dir: Path,
    summary: Dict[str, Any],
    items: List[Dict[str, Any]],
    limit: int,
) -> str:
    rows = items[:limit]

    lines: List[str] = []
    lines.append("# Snapshot Index")
    lines.append(f"- Generated at: {generated_at}")
    lines.append(f"- Snapshots dir: {snapshots_dir}")
    lines.append(
        f"- Total(valid/invalid/size): {summary.get('valid')}/{summary.get('invalid')}/{summary.get('total_size_mb')} MB"
    )
    lines.append("")
    lines.append("常用查找示例：")
    lines.append("- `./prompt-dsl-system/tools/run.sh snapshot-open --trace-id <TRACE_ID>`")
    lines.append("- `./prompt-dsl-system/tools/run.sh snapshot-open --label apply-move --latest`")
    lines.append("")
    lines.append("## Recent Snapshots (latest first)")
    lines.append("| created_at | label | trace_id | snapshot_id | size_mb | path |")
    lines.append("| --- | --- | --- | --- | ---: | --- |")
    if not rows:
        lines.append("| - | - | - | - | - | - |")
    else:
        for item in rows:
            lines.append(
                "| {created_at} | {label} | {trace_id} | {snapshot_id} | {size_mb} | {path} |".format(
                    created_at=item.get("created_at", ""),
                    label=item.get("label", ""),
                    trace_id=item.get("trace_id", ""),
                    snapshot_id=item.get("snapshot_id", ""),
                    size_mb=item.get("size_mb", 0),
                    path=item.get("path", ""),
                )
            )

    if len(items) > limit:
        lines.append("")
        lines.append(f"- 仅展示前 {limit} 条，完整列表见 `snapshot_index.json`。")

    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot indexer")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--policy", default="", help="Optional policy YAML path")
    parser.add_argument("--policy-override", action="append", default=[], help="Policy override key=value")
    parser.add_argument("--snapshots-dir", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--limit", default="")
    parser.add_argument("--include-invalid", default="false")
    parser.add_argument("--now", default="")
    args = parser.parse_args(argv)

    cwd = Path.cwd().resolve()
    repo_root = to_path(str(args.repo_root), cwd)
    policy_overrides = build_cli_override_dict(
        repo_root=repo_root,
        policy_path=str(getattr(args, "policy", "") or "").strip(),
        policy_override_exprs=getattr(args, "policy_override", []) or [],
    )
    policy = load_policy(repo_root, cli_overrides=policy_overrides)

    snapshots_default = str(get_policy_value(policy, "paths.snapshots_dir", "prompt-dsl-system/tools/snapshots") or "prompt-dsl-system/tools/snapshots")
    output_default = str(get_policy_value(policy, "paths.tools_dir", "prompt-dsl-system/tools") or "prompt-dsl-system/tools")
    limit_default = parse_int(get_policy_value(policy, "index.snapshot_limit_md", 500), default=500, minimum=1)

    snapshots_dir = to_path(str(args.snapshots_dir or "").strip() or snapshots_default, repo_root)
    output_dir = to_path(str(args.output_dir or "").strip() or output_default, repo_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    limit = parse_int(args.limit, default=limit_default, minimum=1)
    include_invalid = parse_cli_bool(args.include_invalid, default=False)

    now_ref = parse_iso8601(str(args.now)) if str(args.now).strip() else None
    if str(args.now).strip() and now_ref is None:
        print(f"Invalid --now (expected ISO8601): {args.now}")
        return 2

    valid_items, invalid_entries = discover_snapshots(snapshots_dir)

    valid_items.sort(key=lambda x: x["created_at_dt"], reverse=True)

    labels: Dict[str, int] = {}
    total_size_bytes = 0
    for item in valid_items:
        label = str(item.get("label", ""))
        labels[label] = labels.get(label, 0) + 1
        total_size_bytes += int(item.get("size_bytes", 0))

    json_items = [
        {
            "snapshot_id": item.get("snapshot_id"),
            "path": item.get("path"),
            "created_at": item.get("created_at"),
            "label": item.get("label"),
            "trace_id": item.get("trace_id"),
            "context_id": item.get("context_id"),
            "repo_root": item.get("repo_root"),
            "size_mb": item.get("size_mb"),
        }
        for item in valid_items
    ]

    report: Dict[str, Any] = {
        "generated_at": (now_ref.isoformat() if now_ref else now_iso()),
        "snapshots_dir": str(snapshots_dir),
        "summary": {
            "valid": len(valid_items),
            "invalid": len(invalid_entries),
            "total_size_mb": to_mb(total_size_bytes),
            "labels": labels,
        },
        "items": json_items,
    }

    if include_invalid:
        report["invalid_entries"] = invalid_entries

    index_json = (output_dir / "snapshot_index.json").resolve()
    index_md = (output_dir / "snapshot_index.md").resolve()

    index_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    index_md.write_text(
        build_md(report["generated_at"], snapshots_dir, report["summary"], json_items, limit),
        encoding="utf-8",
    )

    print(f"snapshot_index_json: {index_json}")
    print(f"snapshot_index_md: {index_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
