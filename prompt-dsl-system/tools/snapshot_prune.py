#!/usr/bin/env python3
"""Auditable snapshot pruning tool (default dry-run)."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

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


def is_safe_snapshot_dir(entry: Path, snapshots_dir: Path) -> Tuple[bool, str]:
    try:
        entry_resolved = entry.resolve()
        entry_resolved.relative_to(snapshots_dir.resolve())
    except Exception:
        return False, "outside_snapshots_dir"

    if not entry.is_dir():
        return False, "not_directory"
    if not entry.name.startswith("snapshot_"):
        return False, "name_not_snapshot_prefix"

    manifest = (entry / "manifest.json").resolve()
    if not manifest.exists() or not manifest.is_file():
        return False, "missing_manifest_json"

    return True, "ok"


def calc_dir_size(snapshot_dir: Path) -> Tuple[int, List[str]]:
    warnings: List[str] = []
    total = 0

    for root, dirs, files in __import__("os").walk(snapshot_dir, topdown=True, followlinks=False):
        root_path = Path(root)

        kept_dirs: List[str] = []
        for d in dirs:
            dp = (root_path / d)
            if dp.is_symlink():
                warnings.append(f"skip_symlink_dir:{dp}")
                continue
            kept_dirs.append(d)
        dirs[:] = kept_dirs

        for f in files:
            fp = (root_path / f)
            if fp.is_symlink():
                warnings.append(f"skip_symlink_file:{fp}")
                continue
            try:
                total += fp.stat().st_size
            except OSError:
                warnings.append(f"stat_failed:{fp}")

    return total, warnings


def discover_snapshots(snapshots_dir: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
    valid: List[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []

    if not snapshots_dir.exists() or not snapshots_dir.is_dir():
        return valid, invalid, 0

    entries = sorted(list(snapshots_dir.iterdir()), key=lambda p: p.name)
    total_entries = len(entries)

    for entry in entries:
        ok, reason = is_safe_snapshot_dir(entry, snapshots_dir)
        if not ok:
            invalid.append({"path": str(entry), "reason": reason})
            continue

        manifest_path = (entry / "manifest.json").resolve()
        manifest = safe_read_json(manifest_path)
        if not manifest:
            invalid.append({"path": str(entry), "reason": "manifest_parse_failed"})
            continue

        created_raw = manifest.get("created_at")
        created_dt = parse_iso8601(str(created_raw) if created_raw is not None else "")
        if created_dt is None:
            invalid.append({"path": str(entry), "reason": "invalid_created_at"})
            continue

        label_val = manifest.get("label")
        label = str(label_val) if isinstance(label_val, str) else ""

        size_bytes, size_warnings = calc_dir_size(entry)

        item: Dict[str, Any] = {
            "path": str(entry.resolve()),
            "snapshot_id": str(manifest.get("snapshot_id") or entry.name),
            "created_at": created_dt.isoformat(),
            "created_at_dt": created_dt,
            "label": label,
            "trace_id": str(manifest.get("trace_id") or ""),
            "repo_root": str(manifest.get("repo_root") or ""),
            "size_bytes": int(size_bytes),
            "size_mb": to_mb(size_bytes),
            "warnings": size_warnings,
            "delete": False,
            "reasons": [],
            "status": "skipped",
            "error": None,
        }
        valid.append(item)

    return valid, invalid, total_entries


def apply_filters(
    items: List[Dict[str, Any]],
    only_labels: Set[str],
    exclude_labels: Set[str],
) -> Tuple[List[Dict[str, Any]], Set[str]]:
    candidates: List[Dict[str, Any]] = []
    protected_paths: Set[str] = set()

    for item in items:
        label = str(item.get("label", ""))
        path = str(item.get("path", ""))

        if label in exclude_labels:
            item["status"] = "skipped"
            item["reasons"].append("label_excluded")
            protected_paths.add(path)
            continue

        if only_labels and label not in only_labels:
            item["status"] = "skipped"
            item["reasons"].append("label_not_in_only")
            protected_paths.add(path)
            continue

        candidates.append(item)

    return candidates, protected_paths


def plan_prune(
    items: List[Dict[str, Any]],
    keep_last: int,
    max_total_size_mb: int,
    only_labels: Set[str],
    exclude_labels: Set[str],
) -> Tuple[List[Dict[str, Any]], bool, int, int]:
    sorted_items = sorted(items, key=lambda x: x["created_at_dt"], reverse=True)

    candidates, protected_paths = apply_filters(sorted_items, only_labels, exclude_labels)

    for idx, item in enumerate(candidates):
        if idx < keep_last:
            item["status"] = "skipped"
            item["reasons"].append("kept_by_keep_last")
            protected_paths.add(str(item["path"]))
        else:
            item["delete"] = True
            item["status"] = "planned"
            item["reasons"].append("older_than_keep_last")
            if only_labels:
                item["reasons"].append("label_included")

    total_before = sum(int(x.get("size_bytes", 0)) for x in sorted_items)
    limit_bytes = max_total_size_mb * MB

    planned_deleted_size = sum(int(x.get("size_bytes", 0)) for x in sorted_items if x.get("delete"))
    projected_after = total_before - planned_deleted_size

    unable_to_meet = False
    if total_before > limit_bytes:
        if projected_after > limit_bytes:
            extras = sorted(candidates, key=lambda x: x["created_at_dt"])  # oldest first
            for item in extras:
                p = str(item.get("path", ""))
                if p in protected_paths:
                    continue
                if item.get("delete"):
                    if "size_limit_exceeded" not in item["reasons"]:
                        item["reasons"].append("size_limit_exceeded")
                    continue
                item["delete"] = True
                item["status"] = "planned"
                item["reasons"].append("size_limit_exceeded")
                projected_after -= int(item.get("size_bytes", 0))
                if projected_after <= limit_bytes:
                    break

        if projected_after > limit_bytes:
            unable_to_meet = True

    total_after_planned = total_before - sum(int(x.get("size_bytes", 0)) for x in sorted_items if x.get("delete"))
    return sorted_items, unable_to_meet, total_before, max(total_after_planned, 0)


def execute_delete(items: List[Dict[str, Any]], snapshots_dir: Path) -> int:
    deleted_count = 0
    for item in items:
        if not item.get("delete"):
            if item.get("status") == "planned":
                item["status"] = "skipped"
            continue

        target = Path(str(item.get("path", ""))).resolve()
        ok, reason = is_safe_snapshot_dir(target, snapshots_dir)
        if not ok:
            item["status"] = "error"
            item["error"] = f"safety_check_failed:{reason}"
            continue

        try:
            shutil.rmtree(target)
            item["status"] = "deleted"
            deleted_count += 1
        except OSError as exc:
            item["status"] = "error"
            item["error"] = str(exc)

    return deleted_count


def write_md(report: Dict[str, Any], out_path: Path) -> None:
    policy = report.get("policy") if isinstance(report.get("policy"), dict) else {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    items = report.get("items") if isinstance(report.get("items"), list) else []
    invalids = report.get("invalid_entries_list") if isinstance(report.get("invalid_entries_list"), list) else []

    planned = [x for x in items if isinstance(x, dict) and x.get("delete")]

    lines: List[str] = []
    lines.append("# Snapshot Prune Report")
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- snapshots_dir: {report.get('snapshots_dir')}")
    lines.append("")
    lines.append("## Policy")
    lines.append(f"- keep_last: {policy.get('keep_last')}")
    lines.append(f"- max_total_size_mb: {policy.get('max_total_size_mb')}")
    lines.append(f"- only_label: {policy.get('only_label')}")
    lines.append(f"- exclude_label: {policy.get('exclude_label')}")
    lines.append(f"- dry_run: {summary.get('dry_run')}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- total_entries: {summary.get('total_entries')}")
    lines.append(f"- valid_snapshots: {summary.get('valid_snapshots')}")
    lines.append(f"- invalid_entries: {summary.get('invalid_entries')}")
    lines.append(f"- total_size_mb_before: {summary.get('total_size_mb_before')}")
    lines.append(f"- total_size_mb_after: {summary.get('total_size_mb_after')}")
    lines.append(f"- to_delete: {summary.get('to_delete')}")
    lines.append(f"- deleted: {summary.get('deleted')}")
    lines.append(f"- unable_to_meet_size_limit: {summary.get('unable_to_meet_size_limit')}")
    lines.append("")
    lines.append("## Planned Deletions")
    if not planned:
        lines.append("- none")
    else:
        for item in planned[:20]:
            lines.append(
                f"- {item.get('snapshot_id')} | label={item.get('label')} | size_mb={item.get('size_mb')} | reasons={item.get('reasons')}"
            )
        if len(planned) > 20:
            lines.append(f"- ... and {len(planned) - 20} more (see json)")
    lines.append("")
    lines.append("## Invalid Entries")
    if not invalids:
        lines.append("- none")
    else:
        for inv in invalids[:20]:
            if isinstance(inv, dict):
                lines.append(f"- {inv.get('path')} | reason={inv.get('reason')}")
            else:
                lines.append(f"- {inv}")
        if len(invalids) > 20:
            lines.append(f"- ... and {len(invalids) - 20} more (see json)")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Prune snapshot directories with auditable policy (default dry-run)")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--policy", default="", help="Optional policy YAML path")
    parser.add_argument("--policy-override", action="append", default=[], help="Policy override key=value")
    parser.add_argument("--snapshots-dir", default="")
    parser.add_argument("--keep-last", default="")
    parser.add_argument("--max-total-size-mb", default="")
    parser.add_argument("--only-label", action="append", default=[])
    parser.add_argument("--exclude-label", action="append", default=[])
    parser.add_argument("--dry-run", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output-dir", default="")
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

    snapshots_dir_default = str(get_policy_value(policy, "paths.snapshots_dir", "prompt-dsl-system/tools/snapshots") or "prompt-dsl-system/tools/snapshots")
    output_dir_default = str(get_policy_value(policy, "paths.tools_dir", "prompt-dsl-system/tools") or "prompt-dsl-system/tools")
    keep_last_default = parse_int(get_policy_value(policy, "prune.keep_last", 20), default=20, minimum=0)
    max_total_size_default = parse_int(get_policy_value(policy, "prune.max_total_size_mb", 1024), default=1024, minimum=1)
    dry_run_default = parse_cli_bool(get_policy_value(policy, "prune.dry_run_default", True), default=True)

    snapshots_dir = to_path(str(args.snapshots_dir or "").strip() or snapshots_dir_default, repo_root)
    output_dir = to_path(str(args.output_dir or "").strip() or output_dir_default, repo_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    keep_last = parse_int(args.keep_last, default=keep_last_default, minimum=0)
    max_total_size_mb = parse_int(args.max_total_size_mb, default=max_total_size_default, minimum=1)

    only_labels = {str(x) for x in (args.only_label or [])}
    exclude_labels = {str(x) for x in (args.exclude_label or [])}

    dry_run = parse_cli_bool(args.dry_run, default=dry_run_default)
    if args.apply:
        dry_run = False

    now_ref = parse_iso8601(str(args.now)) if str(args.now or "").strip() else None
    if str(args.now or "").strip() and now_ref is None:
        print(f"Invalid --now (expected ISO8601): {args.now}")
        return 2

    valid_items, invalid_entries, total_entries = discover_snapshots(snapshots_dir)

    planned_items, unable_to_meet, total_before_bytes, total_after_planned_bytes = plan_prune(
        items=valid_items,
        keep_last=keep_last,
        max_total_size_mb=max_total_size_mb,
        only_labels=only_labels,
        exclude_labels=exclude_labels,
    )

    deleted = 0
    if not dry_run:
        deleted = execute_delete(planned_items, snapshots_dir)

    total_after_bytes = total_after_planned_bytes
    if not dry_run:
        total_after_bytes = total_before_bytes - sum(
            int(x.get("size_bytes", 0)) for x in planned_items if x.get("status") == "deleted"
        )

    report: Dict[str, Any] = {
        "generated_at": now_iso(),
        "now_reference": now_ref.isoformat() if now_ref else None,
        "snapshots_dir": str(snapshots_dir),
        "policy": {
            "keep_last": keep_last,
            "max_total_size_mb": max_total_size_mb,
            "only_label": sorted(list(only_labels)),
            "exclude_label": sorted(list(exclude_labels)),
        },
        "summary": {
            "total_entries": total_entries,
            "valid_snapshots": len(planned_items),
            "invalid_entries": len(invalid_entries),
            "total_size_mb_before": to_mb(total_before_bytes),
            "total_size_mb_after": to_mb(max(total_after_bytes, 0)),
            "to_delete": sum(1 for x in planned_items if x.get("delete")),
            "deleted": deleted,
            "dry_run": dry_run,
            "unable_to_meet_size_limit": unable_to_meet,
        },
        "items": [
            {
                "path": x.get("path"),
                "snapshot_id": x.get("snapshot_id"),
                "created_at": x.get("created_at"),
                "label": x.get("label"),
                "size_mb": x.get("size_mb"),
                "delete": bool(x.get("delete")),
                "reasons": x.get("reasons", []),
                "status": x.get("status", "skipped"),
                "error": x.get("error"),
            }
            for x in planned_items
        ],
        "invalid_entries_list": invalid_entries,
    }

    report_json = (output_dir / "snapshot_prune_report.json").resolve()
    report_md = (output_dir / "snapshot_prune_report.md").resolve()
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_md(report, report_md)

    print(f"snapshot_prune_report_json: {report_json}")
    print(f"snapshot_prune_report_md: {report_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
