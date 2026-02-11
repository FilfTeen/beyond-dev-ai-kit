#!/usr/bin/env python3
"""Compare two traces from trace_index and emit structured + readable diff reports."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from policy_loader import build_cli_override_dict, get_policy_value, load_policy


DEFAULT_INDEX_REL = "prompt-dsl-system/tools/trace_index.json"
DEFAULT_TRACE_INDEXER_REL = "prompt-dsl-system/tools/trace_indexer.py"


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


def safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def run_trace_indexer(repo_root: Path, tools_dir: Path, index_output_dir: Path) -> bool:
    script = (repo_root / DEFAULT_TRACE_INDEXER_REL).resolve()
    if not script.exists():
        print(f"trace_indexer not found: {script}", file=sys.stderr)
        return False

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--tools-dir",
        str(tools_dir),
        "--output-dir",
        str(index_output_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode == 0


def match_trace(items: List[Dict[str, Any]], prefix: str, latest: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    matched: List[Dict[str, Any]] = []
    p = prefix.strip()
    for item in items:
        if not isinstance(item, dict):
            continue
        trace_id = str(item.get("trace_id") or "")
        if trace_id.startswith(p):
            matched.append(item)

    matched.sort(
        key=lambda it: parse_iso8601(str(it.get("last_seen_at") or ""))
        or datetime(1970, 1, 1, tzinfo=timezone.utc),
        reverse=True,
    )

    if not matched:
        return None, []
    if len(matched) > 1 and not latest:
        return None, matched
    return matched[0], matched


def count_values(commands: List[Dict[str, Any]], key: str, default: str = "") -> Dict[str, int]:
    c: Counter[str] = Counter()
    for row in commands:
        if not isinstance(row, dict):
            continue
        value = str(row.get(key) or default)
        c[value] += 1
    return dict(c)


def top_key(counts: Dict[str, int]) -> str:
    if not counts:
        return ""
    # Deterministic tie-break by key.
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def ack_total(ack_counts: Dict[str, int]) -> int:
    total = 0
    for k, v in ack_counts.items():
        if str(k).lower() != "none":
            total += int(v)
    return total


def summarize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    commands = item.get("commands") if isinstance(item.get("commands"), list) else []
    paths = item.get("paths") if isinstance(item.get("paths"), dict) else {}
    highlights = item.get("highlights") if isinstance(item.get("highlights"), dict) else {}

    latest_command = ""
    latest_exit_code: Optional[int] = None
    if commands:
        last = commands[-1] if isinstance(commands[-1], dict) else {}
        latest_command = str(last.get("command") or "")
        try:
            latest_exit_code = int(last.get("exit_code"))
        except (TypeError, ValueError):
            latest_exit_code = None

    command_counts = count_values(commands, "command", default="unknown")
    blocked_by_counts = count_values(commands, "blocked_by", default="none")
    verify_status_counts = count_values(commands, "verify_status", default="MISSING")
    ack_used_counts = count_values(commands, "ack_used", default="none")

    bypass = highlights.get("bypass_attempt")
    if not isinstance(bypass, bool):
        bypass = None

    snapshot_paths = paths.get("snapshot_paths") if isinstance(paths.get("snapshot_paths"), list) else []
    snapshot_paths = [str(x) for x in snapshot_paths if isinstance(x, str)]

    return {
        "trace_id": str(item.get("trace_id") or ""),
        "context_id": str(item.get("context_id") or ""),
        "last_seen_at": str(item.get("last_seen_at") or ""),
        "command_counts": command_counts,
        "latest_command": latest_command,
        "latest_exit_code": latest_exit_code,
        "blocked_by_counts": blocked_by_counts,
        "verify_status_counts": verify_status_counts,
        "ack_used_counts": ack_used_counts,
        "verify_top": top_key(verify_status_counts),
        "ack_total": ack_total(ack_used_counts),
        "bypass_attempt": bypass,
        "paths": {
            "deliveries_dir": paths.get("deliveries_dir") if isinstance(paths.get("deliveries_dir"), str) else None,
            "snapshot_paths": snapshot_paths,
            "snapshot_count": len(snapshot_paths),
            "risk_gate_report": paths.get("risk_gate_report") if isinstance(paths.get("risk_gate_report"), str) else None,
            "risk_gate_token": paths.get("risk_gate_token") if isinstance(paths.get("risk_gate_token"), str) else None,
            "verify_report": paths.get("verify_report") if isinstance(paths.get("verify_report"), str) else None,
            "health_report": paths.get("health_report") if isinstance(paths.get("health_report"), str) else None,
            "run_plan": paths.get("run_plan") if isinstance(paths.get("run_plan"), str) else None,
            "validate_report": paths.get("validate_report") if isinstance(paths.get("validate_report"), str) else None,
        },
    }


def diff_counts(a: Dict[str, int], b: Dict[str, int]) -> Dict[str, Dict[str, int]]:
    keys = set(a.keys()) | set(b.keys())
    added: Dict[str, int] = {}
    removed: Dict[str, int] = {}
    net: Dict[str, int] = {}
    for k in sorted(keys):
        av = int(a.get(k, 0))
        bv = int(b.get(k, 0))
        delta = bv - av
        if delta > 0:
            added[k] = delta
        elif delta < 0:
            removed[k] = -delta
        if delta != 0:
            net[k] = delta
    return {"added": added, "removed": removed, "net": net}


def scan_delivery_files(
    repo_root: Path,
    deliveries_rel_path: Optional[str],
    depth: int,
    limit_files: int,
) -> Tuple[Set[str], bool]:
    files: Set[str] = set()
    if not deliveries_rel_path:
        return files, False

    base = (repo_root / deliveries_rel_path).resolve()
    if not base.exists() or not base.is_dir():
        return files, False

    truncated = False
    for root, dirs, filenames in os.walk(base, topdown=True, followlinks=False):
        root_path = Path(root)
        try:
            rel_parts = root_path.relative_to(base).parts
            current_depth = len(rel_parts)
        except ValueError:
            current_depth = 0

        keep_dirs: List[str] = []
        for d in dirs:
            dp = root_path / d
            if dp.is_symlink():
                continue
            if current_depth + 1 <= depth:
                keep_dirs.append(d)
        dirs[:] = keep_dirs

        if current_depth > depth:
            continue

        for name in sorted(filenames):
            fp = root_path / name
            if fp.is_symlink() or not fp.is_file():
                continue
            try:
                rel = fp.relative_to(base).as_posix()
            except ValueError:
                continue
            files.add(rel)
            if len(files) >= limit_files:
                truncated = True
                return files, truncated

    return files, truncated


def build_recommendations(
    a: Dict[str, Any],
    b: Dict[str, Any],
    blocked_diff: Dict[str, Dict[str, int]],
    deliveries_enabled: bool,
    deliveries_added: int,
) -> List[str]:
    recs: List[str] = []

    a_verify_fail = int(a.get("verify_status_counts", {}).get("FAIL", 0))
    b_verify_fail = int(b.get("verify_status_counts", {}).get("FAIL", 0))
    if b_verify_fail > 0 and a_verify_fail == 0:
        recs.append(
            "B 出现 verify FAIL（A 无 FAIL）：先执行 trace-open 定位，再跑 verify-followup-fixes 与 apply-followup-fixes(plan) 收敛残留引用。"
        )

    if int(b.get("ack_total", 0)) > int(a.get("ack_total", 0)):
        recs.append(
            "B 的 ACK 使用次数上升：检查 risk_gate_report 与 ack_notes，确认是否存在 release gate bypass 行为。"
        )

    guard_loop_increase = 0
    for gate_key in ("guard_gate", "loop_gate", "verify_gate", "risk_gate"):
        guard_loop_increase += int(blocked_diff.get("net", {}).get(gate_key, 0))
    none_delta = int(blocked_diff.get("net", {}).get("none", 0))
    if guard_loop_increase > 0 or none_delta < 0:
        recs.append(
            "阻断型 gate 增加或成功执行减少：优先运行 debug-guard，并减少同一问题的反复推进尝试。"
        )

    if deliveries_enabled and deliveries_added >= 50:
        recs.append(
            "deliveries 新增文件较多：建议执行 snapshot-prune/trace-index，避免索引和审计噪声持续扩大。"
        )

    a_exit = a.get("latest_exit_code")
    b_exit = b.get("latest_exit_code")
    if a_exit == 0 and b_exit not in (0, None):
        recs.append(
            "B 最新退出码非 0（A 为 0）：先看 B 的 health_report 与 risk_gate_report，再决定是否继续 run/apply。"
        )

    if not recs:
        recs.append("两次 trace 的关键健康指标接近：继续按 validate -> verify -> run 的顺序执行即可。")

    return recs[:7]


def build_diff(
    repo_root: Path,
    a: Dict[str, Any],
    b: Dict[str, Any],
    scan_deliveries: bool,
    deliveries_depth: int,
    limit_files: int,
) -> Dict[str, Any]:
    blocked_diff = diff_counts(a.get("blocked_by_counts", {}), b.get("blocked_by_counts", {}))
    ack_usage = {
        "a_ack_total": int(a.get("ack_total", 0)),
        "b_ack_total": int(b.get("ack_total", 0)),
    }

    a_paths = a.get("paths", {}) if isinstance(a.get("paths"), dict) else {}
    b_paths = b.get("paths", {}) if isinstance(b.get("paths"), dict) else {}

    reports = ["run_plan", "validate_report", "health_report", "verify_report", "risk_gate_report", "risk_gate_token"]
    missing_in_b: List[str] = []
    for report_key in reports:
        if a_paths.get(report_key) and not b_paths.get(report_key):
            missing_in_b.append(report_key)

    deliveries_part: Dict[str, Any] = {
        "enabled": bool(scan_deliveries),
        "added": [],
        "removed": [],
        "common_count": 0,
        "truncated": False,
    }
    if scan_deliveries:
        files_a, trunc_a = scan_delivery_files(
            repo_root=repo_root,
            deliveries_rel_path=a_paths.get("deliveries_dir"),
            depth=deliveries_depth,
            limit_files=limit_files,
        )
        files_b, trunc_b = scan_delivery_files(
            repo_root=repo_root,
            deliveries_rel_path=b_paths.get("deliveries_dir"),
            depth=deliveries_depth,
            limit_files=limit_files,
        )
        deliveries_part = {
            "enabled": True,
            "added": sorted(list(files_b - files_a)),
            "removed": sorted(list(files_a - files_b)),
            "common_count": len(files_a & files_b),
            "truncated": bool(trunc_a or trunc_b),
        }

    verify_a_top = str(a.get("verify_top") or "MISSING")
    verify_b_top = str(b.get("verify_top") or "MISSING")

    diff_obj: Dict[str, Any] = {
        "latest_exit_code": {
            "a": a.get("latest_exit_code"),
            "b": b.get("latest_exit_code"),
            "changed": a.get("latest_exit_code") != b.get("latest_exit_code"),
        },
        "blocked_by": blocked_diff,
        "verify_status": {
            "a_top": verify_a_top,
            "b_top": verify_b_top,
            "changed": verify_a_top != verify_b_top,
        },
        "ack_usage": ack_usage,
        "paths": {
            "deliveries_dir_changed": a_paths.get("deliveries_dir") != b_paths.get("deliveries_dir"),
            "snapshots_delta": int(b_paths.get("snapshot_count", 0)) - int(a_paths.get("snapshot_count", 0)),
            "reports_missing_in_b": missing_in_b,
        },
        "deliveries_files": deliveries_part,
    }

    recommendations = build_recommendations(
        a=a,
        b=b,
        blocked_diff=blocked_diff,
        deliveries_enabled=bool(deliveries_part.get("enabled")),
        deliveries_added=len(deliveries_part.get("added") or []),
    )

    return {"diff": diff_obj, "recommended_actions": recommendations}


def build_md(report: Dict[str, Any]) -> str:
    a = report.get("a", {}) if isinstance(report.get("a"), dict) else {}
    b = report.get("b", {}) if isinstance(report.get("b"), dict) else {}
    diff = report.get("diff", {}) if isinstance(report.get("diff"), dict) else {}
    deliveries = diff.get("deliveries_files", {}) if isinstance(diff.get("deliveries_files"), dict) else {}

    lines: List[str] = []
    lines.append("# Trace Diff (A vs B)")
    lines.append(
        "- A: {trace} (last_seen={last_seen}, latest_exit={exit_code}, verify_top={verify_top})".format(
            trace=a.get("trace_id", ""),
            last_seen=a.get("last_seen_at", ""),
            exit_code=a.get("latest_exit_code", ""),
            verify_top=a.get("verify_top", "MISSING"),
        )
    )
    lines.append(
        "- B: {trace} (last_seen={last_seen}, latest_exit={exit_code}, verify_top={verify_top})".format(
            trace=b.get("trace_id", ""),
            last_seen=b.get("last_seen_at", ""),
            exit_code=b.get("latest_exit_code", ""),
            verify_top=b.get("verify_top", "MISSING"),
        )
    )
    lines.append("")
    lines.append("## Key Changes")

    latest_exit = diff.get("latest_exit_code", {}) if isinstance(diff.get("latest_exit_code"), dict) else {}
    verify = diff.get("verify_status", {}) if isinstance(diff.get("verify_status"), dict) else {}
    blocked = diff.get("blocked_by", {}) if isinstance(diff.get("blocked_by"), dict) else {}
    ack_usage = diff.get("ack_usage", {}) if isinstance(diff.get("ack_usage"), dict) else {}
    path_diff = diff.get("paths", {}) if isinstance(diff.get("paths"), dict) else {}

    lines.append(
        f"- Exit code: A={latest_exit.get('a')} -> B={latest_exit.get('b')} (changed={latest_exit.get('changed')})"
    )
    lines.append(
        f"- Verify: A={verify.get('a_top')} -> B={verify.get('b_top')} (changed={verify.get('changed')})"
    )
    lines.append(f"- Blocked-by net: {blocked.get('net', {})}")
    lines.append(
        f"- Ack usage: A={ack_usage.get('a_ack_total', 0)} -> B={ack_usage.get('b_ack_total', 0)}"
    )
    lines.append(f"- Snapshots delta (B-A): {path_diff.get('snapshots_delta', 0)}")
    lines.append("")

    lines.append("## Deliveries (optional)")
    lines.append(f"- Enabled: {deliveries.get('enabled', False)}")
    lines.append(f"- Added: {len(deliveries.get('added', []) or [])}")
    lines.append(f"- Removed: {len(deliveries.get('removed', []) or [])}")
    lines.append(f"- Common count: {deliveries.get('common_count', 0)}")
    lines.append(f"- Truncated: {deliveries.get('truncated', False)}")
    added_top = (deliveries.get("added") or [])[:20]
    removed_top = (deliveries.get("removed") or [])[:20]
    if added_top:
        lines.append("- Added top 20:")
        for p in added_top:
            lines.append(f"  - {p}")
    if removed_top:
        lines.append("- Removed top 20:")
        for p in removed_top:
            lines.append(f"  - {p}")
    lines.append("")

    lines.append("## Recommended Next Actions")
    recs = report.get("recommended_actions") if isinstance(report.get("recommended_actions"), list) else []
    if not recs:
        lines.append("1) Continue normal workflow: validate -> verify -> run.")
    else:
        for i, action in enumerate(recs[:7], start=1):
            lines.append(f"{i}) {action}")

    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two traces from trace index")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--policy", default="", help="Optional policy YAML path")
    parser.add_argument("--policy-override", action="append", default=[], help="Policy override key=value")
    parser.add_argument("--tools-dir", default="")
    parser.add_argument("--index", default="")
    parser.add_argument("--a", required=True)
    parser.add_argument("--b", required=True)
    parser.add_argument("--latest", default="true")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--scan-deliveries", default="")
    parser.add_argument("--deliveries-depth", default="")
    parser.add_argument("--limit-files", default="")
    parser.add_argument("--format", choices=["md", "json", "both"], default="both")
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
    index_default = str(get_policy_value(policy, "paths.trace_index_json", DEFAULT_INDEX_REL) or DEFAULT_INDEX_REL)
    scan_default = parse_cli_bool(get_policy_value(policy, "diff.scan_deliveries_default", False), default=False)
    depth_default = parse_int(get_policy_value(policy, "diff.deliveries_depth", 2), default=2, minimum=0)
    limit_default = parse_int(get_policy_value(policy, "diff.limit_files", 400), default=400, minimum=20)

    tools_dir = to_path(str(args.tools_dir).strip() or tools_dir_default, repo_root)
    index_path = to_path(str(args.index), repo_root) if str(args.index).strip() else to_path(index_default, repo_root)
    output_dir = to_path(str(args.output_dir), repo_root) if str(args.output_dir).strip() else tools_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if not index_path.exists() or not index_path.is_file():
        ok = run_trace_indexer(repo_root=repo_root, tools_dir=tools_dir, index_output_dir=index_path.parent)
        if not ok:
            print("Failed to auto-generate trace index", file=sys.stderr)
            return 2
        if not index_path.exists() and index_path.name != "trace_index.json":
            fallback_index = (index_path.parent / "trace_index.json").resolve()
            if fallback_index.exists():
                index_path = fallback_index

    index_data = safe_read_json(index_path)
    items = index_data.get("items") if isinstance(index_data.get("items"), list) else []

    latest = parse_cli_bool(args.latest, default=True)
    a_item, a_candidates = match_trace(items, str(args.a), latest=latest)
    if a_item is None:
        if a_candidates and not latest:
            print("A matched multiple traces; provide a longer prefix or use --latest true", file=sys.stderr)
            for cand in a_candidates[:10]:
                print(f"- {cand.get('trace_id')} | last_seen={cand.get('last_seen_at')}", file=sys.stderr)
        else:
            print(f"A trace not found: {args.a}", file=sys.stderr)
        return 2

    b_item, b_candidates = match_trace(items, str(args.b), latest=latest)
    if b_item is None:
        if b_candidates and not latest:
            print("B matched multiple traces; provide a longer prefix or use --latest true", file=sys.stderr)
            for cand in b_candidates[:10]:
                print(f"- {cand.get('trace_id')} | last_seen={cand.get('last_seen_at')}", file=sys.stderr)
        else:
            print(f"B trace not found: {args.b}", file=sys.stderr)
        return 2

    a_summary = summarize_item(a_item)
    b_summary = summarize_item(b_item)

    scan_deliveries = parse_cli_bool(args.scan_deliveries, default=scan_default)
    deliveries_depth = parse_int(args.deliveries_depth, default=depth_default, minimum=0)
    limit_files = parse_int(args.limit_files, default=limit_default, minimum=20)

    diff_bundle = build_diff(
        repo_root=repo_root,
        a=a_summary,
        b=b_summary,
        scan_deliveries=scan_deliveries,
        deliveries_depth=deliveries_depth,
        limit_files=limit_files,
    )

    report = {
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "a": a_summary,
        "b": b_summary,
        "diff": diff_bundle.get("diff", {}),
        "recommended_actions": diff_bundle.get("recommended_actions", []),
    }

    out_json = (output_dir / "trace_diff.json").resolve()
    out_md = (output_dir / "trace_diff.md").resolve()

    out_format = str(args.format).strip().lower()
    if out_format in {"json", "both"}:
        out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if out_format in {"md", "both"}:
        out_md.write_text(build_md(report), encoding="utf-8")

    print(f"trace_diff_json: {out_json}")
    print(f"trace_diff_md: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
