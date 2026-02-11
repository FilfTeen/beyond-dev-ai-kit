#!/usr/bin/env python3
"""Aggregate trace-centric index from trace history, deliveries, snapshots, and reports."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from policy_loader import build_cli_override_dict, get_policy_value, load_policy

MB = 1024 * 1024
REPORT_ASSOC_WINDOW_SECONDS = 24 * 3600


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


def to_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def to_mb(size_bytes: int) -> float:
    return round(float(size_bytes) / float(MB), 3)


def calc_dir_size(path: Path) -> Tuple[int, List[str]]:
    warnings: List[str] = []
    total = 0
    for root, dirs, files in os.walk(path, topdown=True, followlinks=False):
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


def load_trace_history(path: Path, window: int, scan_all: bool) -> List[Dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []

    raw_lines = path.read_text(encoding="utf-8").splitlines()
    if not scan_all:
        raw_lines = raw_lines[-window:]

    records: List[Dict[str, Any]] = []
    for line in raw_lines:
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            records.append(obj)
    return records


def discover_snapshots(snapshots_dir: Path, repo_root: Path) -> Dict[str, List[Tuple[datetime, str]]]:
    by_trace: Dict[str, List[Tuple[datetime, str]]] = {}
    if not snapshots_dir.exists() or not snapshots_dir.is_dir():
        return by_trace

    for entry in snapshots_dir.iterdir():
        if not entry.is_dir() or not entry.name.startswith("snapshot_"):
            continue
        manifest = safe_read_json((entry / "manifest.json").resolve())
        if not manifest:
            continue
        created = parse_iso8601(str(manifest.get("created_at") or ""))
        trace_id = str(manifest.get("trace_id") or "").strip()
        if created is None or not trace_id:
            continue
        by_trace.setdefault(trace_id, []).append((created, to_rel(entry.resolve(), repo_root)))

    for trace_id, rows in by_trace.items():
        rows.sort(key=lambda x: x[0], reverse=True)
        by_trace[trace_id] = rows
    return by_trace


def pick_delivery_dir(trace_id: str, deliveries_dir: Path, repo_root: Path) -> Optional[str]:
    if not deliveries_dir.exists() or not deliveries_dir.is_dir():
        return None
    matches: List[Path] = []
    for entry in deliveries_dir.iterdir():
        if not entry.is_dir():
            continue
        if entry.name.startswith(trace_id):
            matches.append(entry.resolve())
    if not matches:
        return None
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return to_rel(matches[0], repo_root)


def find_report_in_delivery(delivery_dir: Path, filename: str, repo_root: Path) -> Optional[str]:
    if not delivery_dir.exists() or not delivery_dir.is_dir():
        return None
    candidates = list(delivery_dir.rglob(filename))
    candidates = [p for p in candidates if p.is_file()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return to_rel(candidates[0].resolve(), repo_root)


def build_index(
    repo_root: Path,
    tools_dir: Path,
    trace_history: Path,
    deliveries_dir: Path,
    snapshots_dir: Path,
    window: int,
    scan_all: bool,
    report_mtime_window_seconds: int,
) -> Dict[str, Any]:
    records = load_trace_history(trace_history, window=window, scan_all=scan_all)

    trace_map: Dict[str, Dict[str, Any]] = {}
    command_counts: Dict[str, int] = {}
    failures_exit4 = 0
    failures_nonzero = 0

    for rec in records:
        trace_id = str(rec.get("trace_id") or "").strip()
        if not trace_id:
            continue
        ts = parse_iso8601(str(rec.get("timestamp") or ""))
        if ts is None:
            continue

        ctx = str(rec.get("context_id") or "").strip()
        command = str(rec.get("command") or "").strip() or "unknown"
        exit_code_raw = rec.get("exit_code")
        try:
            exit_code = int(exit_code_raw)
        except (TypeError, ValueError):
            exit_code = 0
        blocked_by = str(rec.get("blocked_by") or "none")
        verify_status = str(rec.get("verify_status") or "MISSING")
        snapshot_path = rec.get("snapshot_path")
        snapshot_path_text = str(snapshot_path).strip() if isinstance(snapshot_path, str) else None
        verify_gate_required = bool(rec.get("verify_gate_required", False))
        ack_used = str(rec.get("ack_used") or "none")

        command_counts[command] = command_counts.get(command, 0) + 1
        if exit_code == 4:
            failures_exit4 += 1
        if exit_code != 0:
            failures_nonzero += 1

        group = trace_map.get(trace_id)
        if group is None:
            group = {
                "trace_id": trace_id,
                "context_id": ctx,
                "last_seen_at_dt": ts,
                "last_seen_at": ts.isoformat(),
                "commands": [],
                "paths": {
                    "deliveries_dir": None,
                    "snapshot_paths": [],
                    "run_plan": None,
                    "validate_report": None,
                    "health_report": None,
                    "verify_report": None,
                    "risk_gate_report": None,
                    "risk_gate_token": None,
                },
                "highlights": {
                    "latest_exit_code": exit_code,
                    "latest_verify_status": verify_status,
                    "bypass_attempt": False,
                    "blocked_by_counts": {},
                },
            }
            trace_map[trace_id] = group
        else:
            if ts > group["last_seen_at_dt"]:
                group["last_seen_at_dt"] = ts
                group["last_seen_at"] = ts.isoformat()
                if ctx:
                    group["context_id"] = ctx

        cmd_row = {
            "ts": ts.isoformat(),
            "command": command,
            "exit_code": exit_code,
            "blocked_by": blocked_by,
            "verify_status": verify_status,
            "snapshot_path": snapshot_path_text,
            "verify_gate_required": verify_gate_required,
            "ack_used": ack_used,
        }
        group["commands"].append(cmd_row)

        blocked_counts = group["highlights"]["blocked_by_counts"]
        blocked_counts[blocked_by] = blocked_counts.get(blocked_by, 0) + 1

    snapshot_assoc = discover_snapshots(snapshots_dir=snapshots_dir, repo_root=repo_root)

    known_reports = {
        "validate_report": (tools_dir / "validate_report.json").resolve(),
        "health_report": (tools_dir / "health_report.json").resolve(),
        "verify_report": (tools_dir / "followup_verify_report.json").resolve(),
        "risk_gate_report": (tools_dir / "risk_gate_report.json").resolve(),
        "risk_gate_token": (tools_dir / "RISK_GATE_TOKEN.json").resolve(),
        "run_plan": (tools_dir / "run_plan.yaml").resolve(),
    }

    for trace_id, group in trace_map.items():
        cmds = group["commands"]
        cmds.sort(key=lambda x: x["ts"])

        if cmds:
            latest = cmds[-1]
            group["highlights"]["latest_exit_code"] = latest.get("exit_code", 0)
            group["highlights"]["latest_verify_status"] = latest.get("verify_status", "MISSING")

        bypass = False
        for row in cmds:
            verify_status = str(row.get("verify_status") or "MISSING").upper()
            verify_gate_required = bool(row.get("verify_gate_required", False))
            blocked_by = str(row.get("blocked_by") or "none")
            ack_used = str(row.get("ack_used") or "none")
            if verify_status == "FAIL" and verify_gate_required and (
                blocked_by != "verify_gate" or ack_used != "none"
            ):
                bypass = True
                break
        group["highlights"]["bypass_attempt"] = bypass

        delivery_rel = pick_delivery_dir(trace_id, deliveries_dir=deliveries_dir, repo_root=repo_root)
        if delivery_rel:
            group["paths"]["deliveries_dir"] = delivery_rel
            delivery_abs = (repo_root / delivery_rel).resolve()
            for k, p in known_reports.items():
                if group["paths"].get(k):
                    continue
                hit = find_report_in_delivery(delivery_abs, p.name, repo_root)
                if hit:
                    group["paths"][k] = hit

        snapshot_rows = snapshot_assoc.get(trace_id, [])
        group["paths"]["snapshot_paths"] = [path for _dt, path in snapshot_rows]

    # Conservative global report binding: choose closest trace by mtime within ±24h.
    trace_last_seen = {
        trace_id: group["last_seen_at_dt"] for trace_id, group in trace_map.items()
    }

    for key, file_path in known_reports.items():
        if not file_path.exists() or not file_path.is_file():
            continue
        try:
            file_dt = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue

        candidates: List[Tuple[float, str]] = []
        for trace_id, ts in trace_last_seen.items():
            diff = abs((ts - file_dt).total_seconds())
            if diff <= report_mtime_window_seconds:
                candidates.append((diff, trace_id))

        if not candidates:
            continue
        candidates.sort(key=lambda x: x[0])
        best_diff = candidates[0][0]
        bests = [tid for diff, tid in candidates if diff == best_diff]
        if len(bests) != 1:
            continue

        chosen = bests[0]
        if trace_map[chosen]["paths"].get(key):
            continue
        trace_map[chosen]["paths"][key] = to_rel(file_path, repo_root)

    items: List[Dict[str, Any]] = []
    for trace_id, group in trace_map.items():
        item = {
            "trace_id": trace_id,
            "context_id": group.get("context_id", ""),
            "last_seen_at": group.get("last_seen_at"),
            "commands": [
                {
                    "ts": row.get("ts"),
                    "command": row.get("command"),
                    "exit_code": row.get("exit_code"),
                    "blocked_by": row.get("blocked_by"),
                    "verify_status": row.get("verify_status"),
                    "snapshot_path": row.get("snapshot_path"),
                }
                for row in group.get("commands", [])
            ],
            "paths": group.get("paths", {}),
            "highlights": group.get("highlights", {}),
            "_last_seen_at_dt": group.get("last_seen_at_dt"),
        }
        items.append(item)

    items.sort(key=lambda x: x.get("_last_seen_at_dt") or datetime(1970, 1, 1, tzinfo=timezone.utc), reverse=True)
    for item in items:
        item.pop("_last_seen_at_dt", None)

    result = {
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "tools_dir": str(tools_dir),
        "summary": {
            "trace_ids": len(items),
            "commands": command_counts,
            "failures": {
                "exit_4": failures_exit4,
                "exit_nonzero": failures_nonzero,
            },
        },
        "items": items,
    }
    return result


def build_md(index_data: Dict[str, Any], limit_md: int) -> str:
    summary = index_data.get("summary") if isinstance(index_data.get("summary"), dict) else {}
    items = index_data.get("items") if isinstance(index_data.get("items"), list) else []

    rows = items[:limit_md]

    lines: List[str] = []
    lines.append("# Trace Index")
    lines.append(f"- Generated at: {index_data.get('generated_at')}")
    lines.append(f"- Repo root: {index_data.get('repo_root')}")
    lines.append(f"- Tools dir: {index_data.get('tools_dir')}")
    lines.append(f"- Trace IDs: {summary.get('trace_ids', 0)}")
    lines.append("")
    lines.append("## Recent Traces")
    lines.append("| last_seen_at | trace_id | last_command | exit | verify | deliveries | snapshots_count |")
    lines.append("| --- | --- | --- | ---: | --- | --- | ---: |")

    if not rows:
        lines.append("| - | - | - | - | - | - | - |")
    else:
        for item in rows:
            commands = item.get("commands") if isinstance(item.get("commands"), list) else []
            last = commands[-1] if commands else {}
            paths = item.get("paths") if isinstance(item.get("paths"), dict) else {}
            snaps = paths.get("snapshot_paths") if isinstance(paths.get("snapshot_paths"), list) else []
            lines.append(
                "| {last_seen_at} | {trace_id} | {last_command} | {exit_code} | {verify} | {deliveries} | {snap_count} |".format(
                    last_seen_at=item.get("last_seen_at", ""),
                    trace_id=item.get("trace_id", ""),
                    last_command=last.get("command", ""),
                    exit_code=last.get("exit_code", ""),
                    verify=last.get("verify_status", ""),
                    deliveries=paths.get("deliveries_dir", ""),
                    snap_count=len(snaps),
                )
            )

    if len(items) > limit_md:
        lines.append("")
        lines.append(f"- Only top {limit_md} shown. See trace_index.json for full data.")

    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build trace index")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--policy", default="", help="Optional policy YAML path")
    parser.add_argument("--policy-override", action="append", default=[], help="Policy override key=value")
    parser.add_argument("--tools-dir", default="")
    parser.add_argument("--trace-history", default="")
    parser.add_argument("--deliveries-dir", default="")
    parser.add_argument("--snapshots-dir", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--window", default="")
    parser.add_argument("--scan-all", default="")
    parser.add_argument("--limit-md", default="")
    args = parser.parse_args(argv)

    cwd = Path.cwd().resolve()
    repo_root = to_path(str(args.repo_root), cwd)

    policy_overrides = build_cli_override_dict(
        repo_root=repo_root,
        policy_path=str(getattr(args, "policy", "") or "").strip(),
        policy_override_exprs=getattr(args, "policy_override", []) or [],
    )
    policy = load_policy(repo_root, cli_overrides=policy_overrides)

    tools_dir_default = str(get_policy_value(policy, "paths.tools_dir", "prompt-dsl-system/tools") or "prompt-dsl-system/tools")
    trace_history_default = str(get_policy_value(policy, "paths.trace_history", f"{tools_dir_default}/trace_history.jsonl") or f"{tools_dir_default}/trace_history.jsonl")
    deliveries_default = str(get_policy_value(policy, "paths.deliveries_dir", f"{tools_dir_default}/deliveries") or f"{tools_dir_default}/deliveries")
    snapshots_default = str(get_policy_value(policy, "paths.snapshots_dir", f"{tools_dir_default}/snapshots") or f"{tools_dir_default}/snapshots")
    window_default = parse_int(get_policy_value(policy, "index.trace_window", 200), default=200, minimum=1)
    scan_all_default = parse_cli_bool(get_policy_value(policy, "index.trace_scan_all", False), default=False)
    limit_md_default = parse_int(get_policy_value(policy, "index.snapshot_limit_md", 200), default=200, minimum=1)
    report_window_hours = parse_int(get_policy_value(policy, "index.report_mtime_window_hours", 24), default=24, minimum=1)
    report_window_seconds = report_window_hours * 3600

    tools_dir = to_path(str(args.tools_dir).strip() or tools_dir_default, repo_root)
    trace_history = to_path(str(args.trace_history).strip() or trace_history_default, repo_root)
    deliveries_dir = to_path(str(args.deliveries_dir).strip() or deliveries_default, repo_root)
    snapshots_dir = to_path(str(args.snapshots_dir).strip() or snapshots_default, repo_root)
    output_dir = to_path(str(args.output_dir).strip() or tools_dir_default, repo_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    window = parse_int(args.window, default=window_default, minimum=1)
    scan_all = parse_cli_bool(args.scan_all, default=scan_all_default)
    limit_md = parse_int(args.limit_md, default=limit_md_default, minimum=1)

    index_data = build_index(
        repo_root=repo_root,
        tools_dir=tools_dir,
        trace_history=trace_history,
        deliveries_dir=deliveries_dir,
        snapshots_dir=snapshots_dir,
        window=window,
        scan_all=scan_all,
        report_mtime_window_seconds=report_window_seconds,
    )

    out_json = (output_dir / "trace_index.json").resolve()
    out_md = (output_dir / "trace_index.md").resolve()
    out_json.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(build_md(index_data, limit_md=limit_md), encoding="utf-8")

    print(f"trace_index_json: {out_json}")
    print(f"trace_index_md: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
