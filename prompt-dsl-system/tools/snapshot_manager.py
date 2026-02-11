#!/usr/bin/env python3
"""Create pre-apply snapshots for safe rollback planning.

Standard-library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from policy_loader import build_cli_override_dict, get_policy_value, load_policy

DEFAULT_OUTPUT_DIR = "prompt-dsl-system/tools/snapshots"
DEFAULT_MAX_COPY_MB = 20
DEFAULT_INPUTS = [
    "prompt-dsl-system/tools/move_report.json",
    "prompt-dsl-system/tools/guard_report.json",
    "prompt-dsl-system/tools/rollback_report.json",
    "prompt-dsl-system/tools/risk_gate_report.json",
    "prompt-dsl-system/tools/RISK_GATE_TOKEN.json",
    "prompt-dsl-system/tools/followup_verify_report.json",
    "prompt-dsl-system/tools/followup_patch_plan.json",
    "prompt-dsl-system/tools/conflict_plan.json",
    "prompt-dsl-system/tools/health_report.json",
]


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def now_utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_int(value: Any, default: int, minimum: int = 1) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if n < minimum:
        return minimum
    return n


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def to_repo_path(repo_root: Path, raw: str) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = (repo_root / p).resolve()
    else:
        p = p.resolve()
    return p


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def sanitize_token(text: Optional[str], fallback: str = "na", max_len: int = 16) -> str:
    raw = str(text or "").strip()
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "", raw)
    if not cleaned:
        cleaned = fallback
    return cleaned[:max_len]


def run_cmd(args: Sequence[str], cwd: Path) -> Tuple[int, str, str]:
    proc = subprocess.run(list(args), cwd=str(cwd), capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def detect_vcs(repo_root: Path) -> Dict[str, Any]:
    git_dir = (repo_root / ".git").exists()
    svn_dir = (repo_root / ".svn").exists()

    if git_dir and command_exists("git"):
        rc, out, err = run_cmd(["git", "-C", str(repo_root), "rev-parse", "--is-inside-work-tree"], repo_root)
        if rc == 0 and out.strip().lower() == "true":
            return {
                "type": "git",
                "detected_by": ".git + git command",
                "git_version": run_cmd(["git", "--version"], repo_root)[1].strip(),
            }
        return {
            "type": "none",
            "detected_by": "git check failed",
            "error": err.strip() or out.strip(),
        }

    if command_exists("svn"):
        if svn_dir:
            return {
                "type": "svn",
                "detected_by": ".svn + svn command",
                "svn_version": run_cmd(["svn", "--version", "--quiet"], repo_root)[1].strip(),
            }
        rc, out, err = run_cmd(["svn", "info"], repo_root)
        if rc == 0:
            return {
                "type": "svn",
                "detected_by": "svn info",
                "svn_version": run_cmd(["svn", "--version", "--quiet"], repo_root)[1].strip(),
            }
        return {
            "type": "none",
            "detected_by": "svn unavailable for repo",
            "error": err.strip() or out.strip(),
        }

    return {
        "type": "none",
        "detected_by": "no git/svn metadata",
    }


def parse_git_status_paths(text: str) -> List[str]:
    paths: List[str] = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if not line:
            continue
        # Porcelain format: XY <path> [-> <path>]
        if line.startswith("?? "):
            p = line[3:].strip()
            if p:
                paths.append(p)
            continue
        if len(line) >= 4:
            payload = line[3:].strip()
            if " -> " in payload:
                payload = payload.split(" -> ", 1)[1].strip()
            if payload:
                paths.append(payload)
    return paths


def collect_git(repo_root: Path) -> Tuple[str, List[str], str, Optional[str]]:
    status_rc, status_out, status_err = run_cmd(["git", "-C", str(repo_root), "status", "--porcelain"], repo_root)
    status_text = status_out if status_rc == 0 else (status_out + "\n" + status_err).strip()

    changed: Set[str] = set(parse_git_status_paths(status_out if status_rc == 0 else ""))
    for cmd in [
        ["git", "-C", str(repo_root), "diff", "--name-only"],
        ["git", "-C", str(repo_root), "ls-files", "-m"],
        ["git", "-C", str(repo_root), "ls-files", "--others", "--exclude-standard"],
    ]:
        rc, out, _ = run_cmd(cmd, repo_root)
        if rc == 0:
            for line in out.splitlines():
                text = line.strip()
                if text:
                    changed.add(text)

    diff_rc, diff_out, diff_err = run_cmd(["git", "-C", str(repo_root), "diff"], repo_root)
    if diff_rc == 0:
        diff_text = diff_out
        diff_reason = None
    else:
        diff_text = "UNAVAILABLE\n"
        diff_reason = diff_err.strip() or "git diff failed"

    if not status_text:
        status_text = "(clean or no git status output)\n"
    if status_rc != 0 and status_err.strip():
        status_text += "\n[error]\n" + status_err.strip() + "\n"

    return status_text, sorted(changed), diff_text, diff_reason


def parse_svn_status_paths(text: str) -> List[str]:
    paths: List[str] = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        if len(line) < 8:
            continue
        path = line[7:].strip()
        if path:
            paths.append(path)
    return paths


def collect_svn(repo_root: Path) -> Tuple[str, List[str], str, Optional[str], Optional[str]]:
    status_rc, status_out, status_err = run_cmd(["svn", "status"], repo_root)
    status_text = status_out if status_rc == 0 else (status_out + "\n" + status_err).strip()
    changed = sorted(set(parse_svn_status_paths(status_out if status_rc == 0 else "")))

    diff_rc, diff_out, diff_err = run_cmd(["svn", "diff"], repo_root)
    if diff_rc == 0:
        diff_text = diff_out
        diff_reason = None
    else:
        diff_text = "UNAVAILABLE\n"
        diff_reason = diff_err.strip() or "svn diff failed"

    externals_warning = None
    if "externals" in (status_err or "").lower() or "external" in (status_err or "").lower():
        externals_warning = "svn externals warning detected; ignored"

    if not status_text:
        status_text = "(clean or no svn status output)\n"
    if status_rc != 0 and status_err.strip():
        status_text += "\n[error]\n" + status_err.strip() + "\n"

    return status_text, changed, diff_text, diff_reason, externals_warning


def collect_none() -> Tuple[str, List[str], str, Optional[str]]:
    return (
        "no vcs detected\n",
        [],
        "UNAVAILABLE\n",
        "no vcs detected",
    )


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def build_default_inputs(repo_root: Path) -> List[Path]:
    files: List[Path] = [to_repo_path(repo_root, p) for p in DEFAULT_INPUTS]

    tools_dir = (repo_root / "prompt-dsl-system" / "tools").resolve()
    candidates = sorted(tools_dir.glob("conflict_plan*.json"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    if candidates:
        files.append(candidates[0].resolve())

    return files


def copy_inputs(
    repo_root: Path,
    inputs_dir: Path,
    candidates: Sequence[Path],
    max_copy_size_mb: int,
) -> Dict[str, Any]:
    ensure_dir(inputs_dir)
    limit_bytes = max_copy_size_mb * 1024 * 1024

    copied: List[str] = []
    missing: List[str] = []
    skipped_large: List[Dict[str, Any]] = []
    copy_errors: List[Dict[str, str]] = []
    seen: Set[str] = set()

    for src in candidates:
        src_resolved = src.resolve()
        key = str(src_resolved)
        if key in seen:
            continue
        seen.add(key)

        if not src_resolved.exists() or not src_resolved.is_file():
            missing.append(to_repo_relative(src_resolved, repo_root))
            continue

        size = src_resolved.stat().st_size
        if size > limit_bytes:
            skipped_large.append(
                {
                    "path": to_repo_relative(src_resolved, repo_root),
                    "size_bytes": int(size),
                    "max_bytes": int(limit_bytes),
                }
            )
            continue

        try:
            rel = to_repo_relative(src_resolved, repo_root)
            # Keep hierarchy under inputs/<repo-relative>
            dest = (inputs_dir / rel).resolve()
            ensure_dir(dest.parent)
            shutil.copy2(src_resolved, dest)
            copied.append(rel)
        except OSError as exc:
            copy_errors.append(
                {
                    "path": to_repo_relative(src_resolved, repo_root),
                    "error": str(exc),
                }
            )

    return {
        "copied": copied,
        "missing": missing,
        "skipped_large_files": skipped_large,
        "copy_errors": copy_errors,
    }


def write_manifest_md(path: Path, manifest: Dict[str, Any]) -> None:
    vcs_type = (manifest.get("vcs") or {}).get("type", "none")
    skipped = manifest.get("skipped", {}) if isinstance(manifest.get("skipped"), dict) else {}
    lines: List[str] = []
    lines.append("# Snapshot Manifest")
    lines.append(f"- snapshot_id: {manifest.get('snapshot_id')}")
    lines.append(f"- created_at: {manifest.get('created_at')}")
    lines.append(f"- label: {manifest.get('label')}")
    lines.append(f"- context_id: {manifest.get('context_id')}")
    lines.append(f"- trace_id: {manifest.get('trace_id')}")
    lines.append(f"- vcs: {vcs_type}")
    lines.append("")
    lines.append("## Artifacts")
    artifacts = manifest.get("artifacts", {}) if isinstance(manifest.get("artifacts"), dict) else {}
    lines.append(f"- status: {artifacts.get('status')}")
    lines.append(f"- changed_files: {artifacts.get('changed_files')}")
    lines.append(f"- diff: {artifacts.get('diff')}")
    lines.append(f"- inputs_dir: {artifacts.get('inputs_dir')}")
    lines.append("")
    lines.append("## Skipped")
    lines.append(f"- missing_inputs: {len(skipped.get('missing_inputs', []))}")
    lines.append(f"- skipped_large_files: {len(skipped.get('skipped_large_files', []))}")
    lines.append(f"- copy_errors: {len(skipped.get('copy_errors', []))}")
    reason = skipped.get("diff_unavailable_reason")
    if reason:
        lines.append(f"- diff_unavailable_reason: {reason}")
    lines.append("")
    lines.append("## Restore Hints")
    lines.append("- Full restore (git, destructive): `git reset --hard && git clean -fd`")
    lines.append("- Partial restore (git): `git restore -- <path>` (or `git checkout -- <path>` on old git)")
    lines.append("- Full restore (svn): `svn revert -R .`")
    lines.append("- Partial restore (svn): `svn revert <path>`")
    lines.append("- If no VCS: use snapshot diff + inputs to apply manual rollback.")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_notes(path: Path) -> None:
    lines = [
        "# Snapshot Notes",
        "",
        "- Why snapshot was created:",
        "- What was applied after snapshot:",
        "- Recovery decision:",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def create_snapshot(
    repo_root: Path,
    output_dir: Path,
    context_id: Optional[str],
    trace_id: Optional[str],
    label: Optional[str],
    include_paths: Sequence[str],
    max_copy_size_mb: int,
) -> Tuple[Path, Dict[str, Any]]:
    ensure_dir(output_dir)

    short = sanitize_token(trace_id or context_id, fallback=secrets.token_hex(4), max_len=16)
    snapshot_id = f"snapshot_{now_utc_stamp()}_{short}"
    snapshot_dir = (output_dir / snapshot_id).resolve()
    ensure_dir(snapshot_dir)

    vcs = detect_vcs(repo_root)
    vcs_type = str(vcs.get("type", "none"))

    if vcs_type == "git":
        status_text, changed_files, diff_text, diff_reason = collect_git(repo_root)
        svn_warning = None
    elif vcs_type == "svn":
        status_text, changed_files, diff_text, diff_reason, svn_warning = collect_svn(repo_root)
    else:
        status_text, changed_files, diff_text, diff_reason = collect_none()
        svn_warning = None

    (snapshot_dir / "vcs_detect.json").write_text(
        json.dumps(vcs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (snapshot_dir / "status.txt").write_text(status_text, encoding="utf-8")
    (snapshot_dir / "changed_files.txt").write_text("\n".join(changed_files) + ("\n" if changed_files else ""), encoding="utf-8")
    (snapshot_dir / "diff.patch").write_text(diff_text if diff_text else "", encoding="utf-8")

    input_candidates = build_default_inputs(repo_root)
    for raw in include_paths:
        text = str(raw).strip()
        if not text:
            continue
        input_candidates.append(to_repo_path(repo_root, text))

    copy_result = copy_inputs(
        repo_root=repo_root,
        inputs_dir=(snapshot_dir / "inputs").resolve(),
        candidates=input_candidates,
        max_copy_size_mb=max_copy_size_mb,
    )

    write_notes((snapshot_dir / "notes.md").resolve())

    skipped: Dict[str, Any] = {
        "missing_inputs": copy_result.get("missing", []),
        "skipped_large_files": copy_result.get("skipped_large_files", []),
        "copy_errors": copy_result.get("copy_errors", []),
    }
    if diff_reason:
        skipped["diff_unavailable_reason"] = diff_reason
    if svn_warning:
        skipped["svn_warning"] = svn_warning

    manifest: Dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "created_at": now_utc_iso(),
        "repo_root": str(repo_root),
        "context_id": context_id,
        "trace_id": trace_id,
        "label": label,
        "vcs": {
            "type": vcs_type,
            "details": vcs,
        },
        "artifacts": {
            "status": "status.txt",
            "changed_files": "changed_files.txt",
            "diff": "diff.patch",
            "inputs_dir": "inputs/",
            "inputs_copied": copy_result.get("copied", []),
            "changed_files_count": len(changed_files),
        },
        "skipped": skipped,
        "restore_hints": [
            "git reset --hard && git clean -fd",
            "svn revert -R .",
            "Rollback single file: git restore -- <path> or svn revert <path>",
        ],
    }

    (snapshot_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_manifest_md((snapshot_dir / "manifest.md").resolve(), manifest)

    return snapshot_dir, manifest


def show_latest(output_dir: Path) -> int:
    if not output_dir.exists() or not output_dir.is_dir():
        print("no snapshots directory")
        return 0
    snapshots = [p for p in output_dir.iterdir() if p.is_dir() and p.name.startswith("snapshot_")]
    if not snapshots:
        print("no snapshots found")
        return 0
    latest = max(snapshots, key=lambda p: p.stat().st_mtime)
    manifest = latest / "manifest.json"
    print(f"latest_snapshot: {latest}")
    if manifest.exists():
        print(f"manifest_json: {manifest}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Snapshot manager for pre-apply safety")
    p.add_argument("--repo-root", required=True)
    p.add_argument("--policy", default="", help="Optional policy YAML path")
    p.add_argument("--policy-override", action="append", default=[], help="Policy override key=value")
    p.add_argument("--output-dir", default="")
    p.add_argument("--context-id")
    p.add_argument("--trace-id")
    p.add_argument("--label")
    p.add_argument("--include", action="append", default=[])
    p.add_argument("--max-copy-size-mb", default="")
    p.add_argument("--mode", default="create", choices=["create", "show"])
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        print(f"Invalid repo root: {repo_root}")
        return 2

    policy_overrides = build_cli_override_dict(
        repo_root=repo_root,
        policy_path=str(getattr(args, "policy", "") or "").strip(),
        policy_override_exprs=getattr(args, "policy_override", []) or [],
    )
    policy = load_policy(repo_root, cli_overrides=policy_overrides)

    output_dir_default = str(get_policy_value(policy, "paths.snapshots_dir", DEFAULT_OUTPUT_DIR) or DEFAULT_OUTPUT_DIR)
    max_copy_default = parse_int(get_policy_value(policy, "snapshots.max_copy_size_mb", DEFAULT_MAX_COPY_MB), default=DEFAULT_MAX_COPY_MB, minimum=1)

    output_dir = to_repo_path(repo_root, str(args.output_dir or "").strip() or output_dir_default)
    max_copy_size_mb = parse_int(args.max_copy_size_mb, default=max_copy_default, minimum=1)

    if args.mode == "show":
        return show_latest(output_dir)

    snapshot_dir, _manifest = create_snapshot(
        repo_root=repo_root,
        output_dir=output_dir,
        context_id=str(args.context_id).strip() if args.context_id else None,
        trace_id=str(args.trace_id).strip() if args.trace_id else None,
        label=str(args.label).strip() if args.label else None,
        include_paths=[str(x) for x in (args.include or [])],
        max_copy_size_mb=max_copy_size_mb,
    )

    print(f"snapshot_path: {to_repo_relative(snapshot_dir, repo_root)}")
    print(f"manifest_json: {to_repo_relative(snapshot_dir / 'manifest.json', repo_root)}")
    print(f"manifest_md: {to_repo_relative(snapshot_dir / 'manifest.md', repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
