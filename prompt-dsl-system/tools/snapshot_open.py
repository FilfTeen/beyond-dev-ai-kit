#!/usr/bin/env python3
"""Find best snapshot match by filters using snapshot index."""

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


def run_indexer(cwd: Path, snapshots_dir: Path, index_path: Path) -> bool:
    script = (cwd / "prompt-dsl-system/tools/snapshot_indexer.py").resolve()
    if not script.exists():
        print(f"snapshot_indexer not found: {script}", file=sys.stderr)
        return False

    output_dir = index_path.parent.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(script),
        "--snapshots-dir",
        str(snapshots_dir),
        "--output-dir",
        str(output_dir),
    ]
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode == 0


def matches(item: Dict[str, Any], args: argparse.Namespace) -> bool:
    if args.snapshot_id and str(item.get("snapshot_id", "")) != str(args.snapshot_id):
        return False
    if args.trace_id and str(item.get("trace_id", "")) != str(args.trace_id):
        return False
    if args.context_id and str(item.get("context_id", "")) != str(args.context_id):
        return False
    if args.label and str(item.get("label", "")) != str(args.label):
        return False
    return True


def build_commands(repo_root: str, snapshot_path: str) -> List[str]:
    return [
        f"./prompt-dsl-system/tools/run.sh snapshot-restore-guide -r {repo_root} --snapshot {snapshot_path}",
        f"cat {snapshot_path}/manifest.md",
        f"open {snapshot_path}  # macOS optional",
    ]


def print_text(best: Dict[str, Any], commands: List[str]) -> None:
    print(f"snapshot path: {best.get('path')}")
    print(f"snapshot_id: {best.get('snapshot_id')}")
    print(f"trace_id: {best.get('trace_id')}")
    print(f"context_id: {best.get('context_id')}")
    print(f"label: {best.get('label')}")
    print(f"created_at: {best.get('created_at')}")
    print("next commands:")
    for c in commands[:2]:
        print(f"- {c}")


def print_md(best: Dict[str, Any], commands: List[str]) -> None:
    print("# Snapshot Match")
    print(f"- path: `{best.get('path')}`")
    print(f"- snapshot_id: `{best.get('snapshot_id')}`")
    print(f"- trace_id: `{best.get('trace_id')}`")
    print(f"- context_id: `{best.get('context_id')}`")
    print(f"- label: `{best.get('label')}`")
    print(f"- created_at: `{best.get('created_at')}`")
    print("")
    print("## Next")
    for c in commands[:2]:
        print(f"- `{c}`")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Find and open snapshots by filters")
    parser.add_argument("--policy", default="", help="Optional policy YAML path")
    parser.add_argument("--policy-override", action="append", default=[], help="Policy override key=value")
    parser.add_argument("--index", default="")
    parser.add_argument("--snapshots-dir", default="")
    parser.add_argument("--trace-id")
    parser.add_argument("--snapshot-id")
    parser.add_argument("--context-id")
    parser.add_argument("--label")
    parser.add_argument("--latest", default="true")
    parser.add_argument("--output", choices=["json", "text", "md"], default="text")
    parser.add_argument("--emit-restore-guide", default="false")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)

    cwd = Path.cwd().resolve()
    repo_root = to_path(str(args.repo_root), cwd)

    policy_overrides = build_cli_override_dict(
        repo_root=repo_root,
        policy_path=str(getattr(args, "policy", "") or "").strip(),
        policy_override_exprs=getattr(args, "policy_override", []) or [],
    )
    policy = load_policy(repo_root, cli_overrides=policy_overrides)

    index_default = str(get_policy_value(policy, "paths.snapshot_index_json", "prompt-dsl-system/tools/snapshot_index.json") or "prompt-dsl-system/tools/snapshot_index.json")
    snapshots_default = str(get_policy_value(policy, "paths.snapshots_dir", "prompt-dsl-system/tools/snapshots") or "prompt-dsl-system/tools/snapshots")

    index_path = to_path(str(args.index or "").strip() or index_default, repo_root)
    snapshots_dir = to_path(str(args.snapshots_dir or "").strip() or snapshots_default, repo_root)

    if not index_path.exists() or not index_path.is_file():
        ok = run_indexer(cwd=repo_root, snapshots_dir=snapshots_dir, index_path=index_path)
        if not ok:
            print("Failed to auto-generate snapshot index", file=sys.stderr)
            return 2

    index_data = safe_read_json(index_path)
    items = index_data.get("items") if isinstance(index_data.get("items"), list) else []

    matched: List[Dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        if matches(raw, args):
            matched.append(raw)

    if not matched:
        print("No matching snapshots. Try running: ./prompt-dsl-system/tools/run.sh snapshot-index", file=sys.stderr)
        return 2

    matched.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)

    latest = parse_cli_bool(args.latest, default=True)
    emit_restore = parse_cli_bool(args.emit_restore_guide, default=False)

    if len(matched) > 1 and not latest:
        subset = matched[:10]
        print(f"matched snapshots: {len(matched)} (showing {len(subset)})")
        for item in subset:
            print(
                f"- {item.get('created_at')} | label={item.get('label')} | trace_id={item.get('trace_id')} | snapshot_id={item.get('snapshot_id')} | path={item.get('path')}"
            )
        return 0

    best = matched[0]
    commands = build_commands(str(repo_root), str(best.get("path", "")))

    if emit_restore:
        print(commands[0])

    if args.output == "json":
        out = {
            "match": best,
            "recommended_commands": commands,
            "matched_count": len(matched),
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
