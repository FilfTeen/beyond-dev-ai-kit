#!/usr/bin/env python3
"""Generate restore guide/scripts from a snapshot directory.

Standard-library only.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


DEFAULT_OUTPUT_SUBDIR = "restore"


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


def run_cmd(cmd: Sequence[str], cwd: Path) -> Tuple[int, str, str]:
    proc = subprocess.run(list(cmd), cwd=str(cwd), capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def command_exists(name: str) -> bool:
    from shutil import which

    return which(name) is not None


def safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def to_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def same_repo_path(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve() or os.path.samefile(str(a.resolve()), str(b.resolve()))
    except OSError:
        return a.resolve() == b.resolve()


def detect_current_vcs(repo_root: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "type": "none",
        "branch": None,
        "url": None,
        "clean": None,
        "status_lines": 0,
        "status_text": "",
        "warnings": [],
    }

    if command_exists("git"):
        rc, out, _err = run_cmd(["git", "rev-parse", "--is-inside-work-tree"], repo_root)
        if rc == 0 and out.strip().lower() == "true":
            result["type"] = "git"
            b_rc, b_out, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_root)
            if b_rc == 0:
                result["branch"] = b_out.strip() or None
            s_rc, s_out, s_err = run_cmd(["git", "status", "--porcelain"], repo_root)
            status_text = s_out if s_rc == 0 else (s_out + "\n" + s_err).strip()
            lines = [line for line in status_text.splitlines() if line.strip()]
            result["status_text"] = status_text
            result["status_lines"] = len(lines)
            result["clean"] = len(lines) == 0
            return result

    if command_exists("svn"):
        rc, out, err = run_cmd(["svn", "info"], repo_root)
        if rc == 0:
            result["type"] = "svn"
            url = None
            for line in out.splitlines():
                if line.startswith("URL:"):
                    url = line.split(":", 1)[1].strip() or None
                    break
            result["url"] = url
            s_rc, s_out, s_err = run_cmd(["svn", "status"], repo_root)
            status_text = s_out if s_rc == 0 else (s_out + "\n" + s_err).strip()
            lines = [line for line in status_text.splitlines() if line.strip()]
            result["status_text"] = status_text
            result["status_lines"] = len(lines)
            result["clean"] = len(lines) == 0
            if s_err.strip() and "extern" in s_err.lower():
                result["warnings"].append("svn externals warning detected")
            return result
        if err.strip():
            result["warnings"].append(err.strip())

    result["status_text"] = "no vcs detected"
    return result


def read_changed_files(path: Path) -> List[str]:
    if not path.exists() or not path.is_file():
        return []
    files: List[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        text = raw.strip()
        if text:
            files.append(text)
    return files


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def compare_snapshot_and_current(
    repo_root: Path,
    snapshot_manifest: Dict[str, Any],
    snapshot_vcs_detect: Dict[str, Any],
    current_vcs: Dict[str, Any],
    strict: bool,
) -> Tuple[str, List[str], bool]:
    warnings: List[str] = []
    strict_mismatch = False

    snapshot_repo = snapshot_manifest.get("repo_root")
    if isinstance(snapshot_repo, str) and snapshot_repo.strip():
        snapshot_repo_path = Path(snapshot_repo).resolve()
        if not same_repo_path(repo_root, snapshot_repo_path):
            strict_mismatch = True
            warnings.append(
                f"snapshot repo_root mismatch: snapshot={snapshot_repo_path} current={repo_root.resolve()}"
            )

    snapshot_vcs_type = "none"
    if isinstance(snapshot_manifest.get("vcs"), dict):
        snapshot_vcs_type = str(snapshot_manifest["vcs"].get("type", "none"))

    current_type = str(current_vcs.get("type", "none"))
    if snapshot_vcs_type != current_type:
        warnings.append(f"vcs type changed: snapshot={snapshot_vcs_type} current={current_type}")

    snapshot_branch = None
    if isinstance(snapshot_vcs_detect.get("current_branch"), str):
        snapshot_branch = snapshot_vcs_detect.get("current_branch")
    elif isinstance(snapshot_vcs_detect.get("details"), dict):
        val = snapshot_vcs_detect["details"].get("current_branch")
        if isinstance(val, str):
            snapshot_branch = val

    current_branch = current_vcs.get("branch")
    if snapshot_branch and isinstance(current_branch, str) and snapshot_branch != current_branch:
        warnings.append(f"branch changed: snapshot={snapshot_branch} current={current_branch}")

    snapshot_url = None
    if isinstance(snapshot_vcs_detect.get("url"), str):
        snapshot_url = snapshot_vcs_detect.get("url")
    elif isinstance(snapshot_vcs_detect.get("details"), dict):
        val = snapshot_vcs_detect["details"].get("url")
        if isinstance(val, str):
            snapshot_url = val

    current_url = current_vcs.get("url")
    if snapshot_url and isinstance(current_url, str) and snapshot_url != current_url:
        warnings.append(f"svn url changed: snapshot={snapshot_url} current={current_url}")

    if current_vcs.get("clean") is False:
        warnings.append("working tree is dirty")

    if strict and strict_mismatch:
        return "FAIL", warnings, strict_mismatch
    if warnings:
        return "WARN", warnings, strict_mismatch
    return "PASS", warnings, strict_mismatch


def generate_restore_full_script(
    shell: str,
    repo_root: Path,
    snapshot_id: str,
    dry_run_default: bool,
    vcs_type: str,
) -> str:
    shebang = "#!/usr/bin/env zsh" if shell == "zsh" else "#!/usr/bin/env bash"
    dry_val = "1" if dry_run_default else "0"

    lines: List[str] = []
    lines.append(shebang)
    lines.append("set -euo pipefail")
    lines.append(f'REPO_ROOT="{repo_root.resolve()}"')
    lines.append(f'SNAPSHOT_ID="{snapshot_id}"')
    lines.append(f'DRY_RUN="${{DRY_RUN:-{dry_val}}}"')
    lines.append("")
    lines.append('echo "[restore] snapshot=${SNAPSHOT_ID} repo=${REPO_ROOT}"')
    lines.append('echo "[restore][WARN] destructive restore may discard uncommitted changes."')
    lines.append('if [ "${DRY_RUN}" != "0" ]; then')
    lines.append('  echo "[restore] DRY_RUN=${DRY_RUN} (preview only). Set DRY_RUN=0 to execute."')
    lines.append("fi")
    lines.append('cd "${REPO_ROOT}"')
    lines.append("")
    lines.append("run_cmd() {")
    lines.append("  if [ \"${DRY_RUN}\" = \"0\" ]; then")
    lines.append("    \"$@\"")
    lines.append("  else")
    lines.append('    echo "[dry-run] $*"')
    lines.append("  fi")
    lines.append("}")
    lines.append("")

    if vcs_type == "git":
        lines.append("run_cmd git reset --hard")
        lines.append("run_cmd git clean -fd")
        lines.append("git status --short || true")
        lines.append('echo "[restore] done (git full restore)."')
    elif vcs_type == "svn":
        lines.append("run_cmd svn revert -R .")
        lines.append("svn status || true")
        lines.append('echo "[restore] done (svn full restore)."')
    else:
        lines.append('echo "[restore][ERROR] no vcs detected; full auto-restore unavailable." >&2')
        lines.append("if [ \"${DRY_RUN}\" = \"0\" ]; then")
        lines.append("  exit 2")
        lines.append("fi")

    return "\n".join(lines) + "\n"


def generate_restore_files_script(
    shell: str,
    repo_root: Path,
    snapshot_id: str,
    changed_files_path: Path,
    dry_run_default: bool,
    vcs_type: str,
) -> str:
    shebang = "#!/usr/bin/env zsh" if shell == "zsh" else "#!/usr/bin/env bash"
    dry_val = "1" if dry_run_default else "0"

    lines: List[str] = []
    lines.append(shebang)
    lines.append("set -euo pipefail")
    lines.append(f'REPO_ROOT="{repo_root.resolve()}"')
    lines.append(f'SNAPSHOT_ID="{snapshot_id}"')
    lines.append(f'CHANGED_FILES_FILE="{changed_files_path.resolve()}"')
    lines.append(f'DRY_RUN="${{DRY_RUN:-{dry_val}}}"')
    lines.append("SKIPPED=0")
    lines.append("")
    lines.append('echo "[restore] snapshot=${SNAPSHOT_ID} repo=${REPO_ROOT}"')
    lines.append('echo "[restore] target list: ${CHANGED_FILES_FILE}"')
    lines.append('echo "[restore][WARN] file-level restore may discard uncommitted changes for listed files."')
    lines.append('if [ "${DRY_RUN}" != "0" ]; then')
    lines.append('  echo "[restore] DRY_RUN=${DRY_RUN} (preview only). Set DRY_RUN=0 to execute."')
    lines.append("fi")
    lines.append('cd "${REPO_ROOT}"')
    lines.append("")
    lines.append('if [ ! -f "${CHANGED_FILES_FILE}" ]; then')
    lines.append('  echo "[restore][ERROR] changed files list not found: ${CHANGED_FILES_FILE}" >&2')
    lines.append("  exit 2")
    lines.append("fi")
    lines.append("")
    lines.append("run_cmd() {")
    lines.append("  if [ \"${DRY_RUN}\" = \"0\" ]; then")
    lines.append("    \"$@\"")
    lines.append("  else")
    lines.append('    echo "[dry-run] $*"')
    lines.append("  fi")
    lines.append("}")
    lines.append("")

    if vcs_type not in {"git", "svn"}:
        lines.append('echo "[restore][ERROR] no vcs detected; file-level auto-restore unavailable." >&2')
        lines.append("if [ \"${DRY_RUN}\" = \"0\" ]; then")
        lines.append("  exit 2")
        lines.append("fi")
        return "\n".join(lines) + "\n"

    lines.append('while IFS= read -r file || [ -n "$file" ]; do')
    lines.append('  [ -z "$file" ] && continue')
    lines.append('  if [ ! -e "$file" ] && [ ! -L "$file" ]; then')
    lines.append('    echo "[restore][skip] missing file: $file"')
    lines.append('    SKIPPED=$((SKIPPED+1))')
    lines.append('    continue')
    lines.append("  fi")

    if vcs_type == "git":
        lines.append('  run_cmd git checkout -- "$file"')
    else:
        lines.append('  run_cmd svn revert "$file"')

    lines.append('done < "${CHANGED_FILES_FILE}"')
    lines.append("")
    lines.append('echo "[restore] skipped files: ${SKIPPED}"')
    if vcs_type == "git":
        lines.append("git status --short || true")
    else:
        lines.append("svn status || true")
    lines.append('echo "[restore] done (file-level restore)."')
    return "\n".join(lines) + "\n"


def generate_restore_guide_md(
    repo_root: Path,
    snapshot_dir: Path,
    output_dir: Path,
    manifest: Dict[str, Any],
    check: Dict[str, Any],
    strict: bool,
) -> str:
    summary = check.get("summary") if isinstance(check.get("summary"), dict) else {}
    status = str(summary.get("status", "WARN"))
    warnings = summary.get("warnings") if isinstance(summary.get("warnings"), list) else []

    snapshot_id = manifest.get("snapshot_id") or snapshot_dir.name
    created_at = manifest.get("created_at")
    trace_id = manifest.get("trace_id")
    label = manifest.get("label")
    vcs = manifest.get("vcs") if isinstance(manifest.get("vcs"), dict) else {}
    vcs_type = str(vcs.get("type", "none"))

    restore_files = (output_dir / "restore_files.sh").resolve()
    restore_full = (output_dir / "restore_full.sh").resolve()
    changed_files_rel = to_relative((snapshot_dir / "changed_files.txt").resolve(), repo_root)

    lines: List[str] = []
    lines.append("# Snapshot Restore Guide")
    lines.append(f"- Snapshot: `{snapshot_id}`")
    lines.append(f"- Created at: `{created_at}`")
    lines.append(f"- Trace ID: `{trace_id}`")
    lines.append(f"- Label: `{label}`")
    lines.append(f"- Snapshot dir: `{snapshot_dir}`")
    lines.append(f"- VCS: `{vcs_type}`")
    lines.append(f"- Strict mode: `{strict}`")
    lines.append("")
    lines.append("## Current Repo Check")
    lines.append(f"- Status: **{status}**")
    if warnings:
        lines.append("- Warnings:")
        for item in warnings[:8]:
            lines.append(f"  - {item}")
    else:
        lines.append("- Warnings: none")
    lines.append("")
    lines.append("## Recommended Order")
    lines.append("1. 优先按文件回滚：`restore_files.sh`")
    lines.append("2. 若仍不一致，再做全量回滚：`restore_full.sh`")
    lines.append("")
    lines.append("## Commands")
    lines.append("```bash")
    lines.append(f"# preview only (default)\n{restore_files}")
    lines.append(f"# execute for real\nDRY_RUN=0 {restore_files}")
    lines.append("")
    lines.append(f"# full restore preview\n{restore_full}")
    lines.append(f"# full restore execute\nDRY_RUN=0 {restore_full}")
    lines.append("```")
    lines.append("")
    lines.append("## Inputs")
    lines.append(f"- changed_files list: `{changed_files_rel}`")
    lines.append("- diff patch: `diff.patch` (under snapshot dir)")
    lines.append("")
    lines.append("## Troubleshooting")
    lines.append("- svn tree conflicts: run `svn status`, resolve conflicts, then retry restore script.")
    lines.append("- git untracked leftovers: after review, use `git clean -fd` (destructive).")
    lines.append("- strict mismatch: verify you are in the same repo root as snapshot manifest.")

    return "\n".join(lines) + "\n"


def build_restore_check(
    repo_root: Path,
    snapshot_dir: Path,
    manifest: Dict[str, Any],
    snapshot_vcs_detect: Dict[str, Any],
    strict: bool,
) -> Dict[str, Any]:
    current_vcs = detect_current_vcs(repo_root)
    status, warnings, strict_mismatch = compare_snapshot_and_current(
        repo_root=repo_root,
        snapshot_manifest=manifest,
        snapshot_vcs_detect=snapshot_vcs_detect,
        current_vcs=current_vcs,
        strict=strict,
    )

    changed_files_path = (snapshot_dir / "changed_files.txt").resolve()
    changed_files = read_changed_files(changed_files_path)

    result: Dict[str, Any] = {
        "generated_at": now_iso(),
        "repo_root": str(repo_root.resolve()),
        "snapshot_path": str(snapshot_dir.resolve()),
        "strict": bool(strict),
        "snapshot": {
            "snapshot_id": manifest.get("snapshot_id") or snapshot_dir.name,
            "created_at": manifest.get("created_at"),
            "trace_id": manifest.get("trace_id"),
            "label": manifest.get("label"),
            "repo_root": manifest.get("repo_root"),
            "vcs_type": (manifest.get("vcs") or {}).get("type") if isinstance(manifest.get("vcs"), dict) else "none",
        },
        "current": {
            "vcs": current_vcs,
        },
        "comparison": {
            "strict_mismatch": strict_mismatch,
            "warnings": warnings,
        },
        "changed_files": {
            "path": str(changed_files_path),
            "count": len(changed_files),
            "sample": changed_files[:20],
        },
        "summary": {
            "status": status,
            "warnings": warnings,
        },
    }
    return result


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate restore guides/scripts from snapshot artifacts")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--snapshot", required=True, help="Snapshot directory path")
    parser.add_argument("--output-dir", help="Output directory (default: <snapshot>/restore)")
    parser.add_argument("--shell", choices=["bash", "zsh"], default="bash")
    parser.add_argument("--mode", choices=["generate", "check"], default="generate")
    parser.add_argument("--strict", default="true", help="true/false, default true")
    parser.add_argument("--dry-run", default="true", help="true/false, default true")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        print(f"Invalid repo root: {repo_root}")
        return 2

    snapshot_path = Path(args.snapshot)
    if not snapshot_path.is_absolute():
        snapshot_path = (repo_root / snapshot_path).resolve()
    else:
        snapshot_path = snapshot_path.resolve()
    if not snapshot_path.exists() or not snapshot_path.is_dir():
        print(f"Snapshot directory not found: {snapshot_path}")
        return 2

    manifest_path = (snapshot_path / "manifest.json").resolve()
    if not manifest_path.exists() or not manifest_path.is_file():
        print(f"manifest.json not found under snapshot: {manifest_path}")
        return 2

    strict = parse_cli_bool(args.strict, default=True)
    dry_run_default = parse_cli_bool(args.dry_run, default=True)

    if args.output_dir and str(args.output_dir).strip():
        output_dir = Path(str(args.output_dir).strip())
        if not output_dir.is_absolute():
            output_dir = (repo_root / output_dir).resolve()
        else:
            output_dir = output_dir.resolve()
    else:
        output_dir = (snapshot_path / DEFAULT_OUTPUT_SUBDIR).resolve()

    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = safe_read_json(manifest_path)
    if not manifest:
        print(f"Failed to parse manifest.json: {manifest_path}")
        return 2
    snapshot_vcs_detect = safe_read_json((snapshot_path / "vcs_detect.json").resolve())

    restore_check = build_restore_check(
        repo_root=repo_root,
        snapshot_dir=snapshot_path,
        manifest=manifest,
        snapshot_vcs_detect=snapshot_vcs_detect,
        strict=strict,
    )

    check_path = (output_dir / "restore_check.json").resolve()
    check_path.write_text(json.dumps(restore_check, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"restore_check_json: {to_relative(check_path, repo_root)}")

    status = str((restore_check.get("summary") or {}).get("status", "WARN"))
    if strict and status == "FAIL":
        print("[restore-guide][error] strict repo mismatch detected; refusing to generate apply scripts.")
        return 2

    if args.mode == "check":
        return 0

    snapshot_id = str(manifest.get("snapshot_id") or snapshot_path.name)
    vcs_type = str(((manifest.get("vcs") if isinstance(manifest.get("vcs"), dict) else {}) or {}).get("type", "none"))

    restore_full_path = (output_dir / "restore_full.sh").resolve()
    restore_files_path = (output_dir / "restore_files.sh").resolve()
    restore_guide_path = (output_dir / "restore_guide.md").resolve()

    full_script = generate_restore_full_script(
        shell=args.shell,
        repo_root=repo_root,
        snapshot_id=snapshot_id,
        dry_run_default=dry_run_default,
        vcs_type=vcs_type,
    )
    files_script = generate_restore_files_script(
        shell=args.shell,
        repo_root=repo_root,
        snapshot_id=snapshot_id,
        changed_files_path=(snapshot_path / "changed_files.txt").resolve(),
        dry_run_default=dry_run_default,
        vcs_type=vcs_type,
    )
    guide_md = generate_restore_guide_md(
        repo_root=repo_root,
        snapshot_dir=snapshot_path,
        output_dir=output_dir,
        manifest=manifest,
        check=restore_check,
        strict=strict,
    )

    write_executable(restore_full_path, full_script)
    write_executable(restore_files_path, files_script)
    restore_guide_path.write_text(guide_md, encoding="utf-8")

    print(f"restore_guide_md: {to_relative(restore_guide_path, repo_root)}")
    print(f"restore_full_sh: {to_relative(restore_full_path, repo_root)}")
    print(f"restore_files_sh: {to_relative(restore_files_path, repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
