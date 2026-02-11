#!/usr/bin/env python3
"""Open aggregated trace chain from trace index."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from policy_loader import build_cli_override_dict, get_policy_value, load_policy


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


def to_path(raw: str, base: Path) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = (base / p).resolve()
    else:
        p = p.resolve()
    return p


def safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def run_trace_indexer(repo_root: Path, tools_dir: Path, index_path: Path) -> bool:
    script = (repo_root / "prompt-dsl-system/tools/trace_indexer.py").resolve()
    if not script.exists():
        print(f"trace_indexer not found: {script}", file=sys.stderr)
        return False
    output_dir = index_path.parent.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--tools-dir",
        str(tools_dir),
        "--output-dir",
        str(output_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode == 0


def find_matches(items: List[Dict[str, Any]], trace_id_prefix: str) -> List[Dict[str, Any]]:
    prefix = trace_id_prefix.strip()
    matched: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        trace_id = str(item.get("trace_id") or "")
        if trace_id.startswith(prefix):
            matched.append(item)
    matched.sort(key=lambda x: str(x.get("last_seen_at") or ""), reverse=True)
    return matched


def build_recommended_commands(
    repo_root: Path,
    trace_id: str,
    paths: Dict[str, Any],
    latest_verify_status: str,
    emit_restore: bool,
    emit_verify: bool,
) -> List[str]:
    commands: List[str] = []

    health_report = paths.get("health_report")
    if isinstance(health_report, str) and health_report.strip():
        commands.append(f"cat {health_report}")
    else:
        commands.append(f"./prompt-dsl-system/tools/run.sh validate -r {repo_root}")

    risk_report = paths.get("risk_gate_report")
    if isinstance(risk_report, str) and risk_report.strip():
        commands.append(f"cat {risk_report}")
    else:
        commands.append(f"./prompt-dsl-system/tools/run.sh trace-index -r {repo_root}")

    risk_token = paths.get("risk_gate_token")
    if isinstance(risk_token, str) and risk_token.strip():
        commands.append(f"cat {risk_token}")
    else:
        commands.append("echo 'risk gate token not linked for this trace'")

    verify_status = str(latest_verify_status or "MISSING").upper()
    if emit_verify and verify_status in {"WARN", "FAIL", "MISSING"}:
        commands.append(
            f"./prompt-dsl-system/tools/run.sh verify-followup-fixes -r {repo_root} --moves <MOVES_JSON>"
        )
    else:
        commands.append("echo 'verify status already PASS (or verify command suppressed)'")

    snap_paths = paths.get("snapshot_paths") if isinstance(paths.get("snapshot_paths"), list) else []
    if emit_restore and snap_paths:
        commands.append(
            f"./prompt-dsl-system/tools/run.sh snapshot-restore-guide -r {repo_root} --snapshot {snap_paths[0]}"
        )
    else:
        commands.append(f"./prompt-dsl-system/tools/run.sh snapshot-index -r {repo_root}")

    commands.append(f"./prompt-dsl-system/tools/run.sh snapshot-open --repo-root {repo_root} --trace-id {trace_id}")

    deliveries_dir = paths.get("deliveries_dir")
    if isinstance(deliveries_dir, str) and deliveries_dir.strip():
        commands.append(f"open {deliveries_dir}  # macOS optional")

    return commands


def print_text(match: Dict[str, Any], commands: List[str]) -> None:
    paths = match.get("paths") if isinstance(match.get("paths"), dict) else {}

    print(f"trace_id: {match.get('trace_id')}")
    print(f"context_id: {match.get('context_id')}")
    print(f"last_seen_at: {match.get('last_seen_at')}")
    print("paths:")
    print(f"- deliveries_dir: {paths.get('deliveries_dir')}")
    print(f"- snapshot_paths: {paths.get('snapshot_paths')}")
    print(f"- run_plan: {paths.get('run_plan')}")
    print(f"- validate_report: {paths.get('validate_report')}")
    print(f"- health_report: {paths.get('health_report')}")
    print(f"- verify_report: {paths.get('verify_report')}")
    print(f"- risk_gate_report: {paths.get('risk_gate_report')}")
    print(f"- risk_gate_token: {paths.get('risk_gate_token')}")
    print("next commands:")
    for cmd in commands[:8]:
        print(f"- {cmd}")


def print_md(match: Dict[str, Any], commands: List[str]) -> None:
    paths = match.get("paths") if isinstance(match.get("paths"), dict) else {}

    print("# Trace Open")
    print(f"- trace_id: `{match.get('trace_id')}`")
    print(f"- context_id: `{match.get('context_id')}`")
    print(f"- last_seen_at: `{match.get('last_seen_at')}`")
    print("")
    print("## Paths")
    print(f"- deliveries_dir: `{paths.get('deliveries_dir')}`")
    print(f"- snapshot_paths: `{paths.get('snapshot_paths')}`")
    print(f"- run_plan: `{paths.get('run_plan')}`")
    print(f"- validate_report: `{paths.get('validate_report')}`")
    print(f"- health_report: `{paths.get('health_report')}`")
    print(f"- verify_report: `{paths.get('verify_report')}`")
    print(f"- risk_gate_report: `{paths.get('risk_gate_report')}`")
    print(f"- risk_gate_token: `{paths.get('risk_gate_token')}`")
    print("")
    print("## Next Commands")
    for cmd in commands[:8]:
        print(f"- `{cmd}`")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Open trace chain by trace-id")
    parser.add_argument("--policy", default="", help="Optional policy YAML path")
    parser.add_argument("--policy-override", action="append", default=[], help="Policy override key=value")
    parser.add_argument("--index", default="")
    parser.add_argument("--trace-id", required=True)
    parser.add_argument("--tools-dir", default="")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--output", choices=["text", "json", "md"], default="text")
    parser.add_argument("--emit-restore", default="true")
    parser.add_argument("--emit-verify", default="true")
    parser.add_argument("--latest", default="true")
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
    index_default = str(get_policy_value(policy, "paths.trace_index_json", f"{tools_dir_default}/trace_index.json") or f"{tools_dir_default}/trace_index.json")

    tools_dir = to_path(str(args.tools_dir).strip() or tools_dir_default, repo_root)

    index_path = to_path(str(args.index), repo_root) if str(args.index).strip() else to_path(index_default, repo_root)

    if not index_path.exists() or not index_path.is_file():
        ok = run_trace_indexer(repo_root=repo_root, tools_dir=tools_dir, index_path=index_path)
        if not ok:
            print("Failed to auto-generate trace index", file=sys.stderr)
            return 2

    index_data = safe_read_json(index_path)
    items = index_data.get("items") if isinstance(index_data.get("items"), list) else []

    matches = find_matches(items, trace_id_prefix=str(args.trace_id))
    if not matches:
        print("No matching trace_id. Try: ./prompt-dsl-system/tools/run.sh trace-index -r .", file=sys.stderr)
        return 2

    latest = parse_cli_bool(args.latest, default=True)
    if len(matches) > 1 and not latest:
        subset = matches[:10]
        print(f"matched traces: {len(matches)} (showing {len(subset)})")
        for item in subset:
            cmds = item.get("commands") if isinstance(item.get("commands"), list) else []
            last_cmd = cmds[-1].get("command") if cmds else ""
            print(
                f"- {item.get('last_seen_at')} | trace_id={item.get('trace_id')} | context_id={item.get('context_id')} | last_command={last_cmd}"
            )
        return 0

    best = matches[0]
    highlights = best.get("highlights") if isinstance(best.get("highlights"), dict) else {}
    latest_verify_status = str(highlights.get("latest_verify_status") or "MISSING")

    commands = build_recommended_commands(
        repo_root=repo_root,
        trace_id=str(best.get("trace_id") or ""),
        paths=best.get("paths") if isinstance(best.get("paths"), dict) else {},
        latest_verify_status=latest_verify_status,
        emit_restore=parse_cli_bool(args.emit_restore, default=True),
        emit_verify=parse_cli_bool(args.emit_verify, default=True),
    )

    if args.output == "json":
        out = {
            "match": best,
            "recommended_commands": commands,
            "matched_count": len(matches),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.output == "md":
        print_md(best, commands)
        return 0

    print_text(best, commands)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
