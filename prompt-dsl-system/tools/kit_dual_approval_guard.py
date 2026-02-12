#!/usr/bin/env python3
"""Gate baseline changes with dual-approval evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

EXIT_INVALID_INPUT = 2
EXIT_APPROVAL_FAIL = 30

DEFAULT_WATCH_FILES = [
    "prompt-dsl-system/tools/kit_integrity_manifest.json",
    "prompt-dsl-system/tools/pipeline_trust_whitelist.json",
]


def parse_bool(value: Any, default: bool = False) -> bool:
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


def parse_watch_files(raw: str) -> List[str]:
    parts = []
    seen = set()
    for item in str(raw or "").split(","):
        rel = str(item).strip().replace("\\", "/")
        if not rel or rel in seen:
            continue
        seen.add(rel)
        parts.append(rel)
    return parts


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def collect_watch_state(repo_root: Path, watch_files: List[str]) -> Tuple[List[Dict[str, Any]], str]:
    state: List[Dict[str, Any]] = []
    for rel in sorted(watch_files):
        fp = (repo_root / rel).resolve()
        if fp.is_file():
            state.append(
                {
                    "path": rel,
                    "exists": True,
                    "sha256": sha256_file(fp),
                    "size": int(fp.stat().st_size),
                }
            )
        else:
            state.append(
                {
                    "path": rel,
                    "exists": False,
                    "sha256": "",
                    "size": 0,
                }
            )

    fingerprint = hashlib.sha256(canonical_json(state).encode("utf-8")).hexdigest()
    return state, fingerprint


def git_changed_watch_files(repo_root: Path, watch_files: List[str]) -> Tuple[bool, List[str], str]:
    cmd = ["git", "-C", str(repo_root), "status", "--porcelain", "--"] + watch_files
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        return False, [], str(exc)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or f"git status exit={proc.returncode}"
        return False, [], detail

    changed: List[str] = []
    for raw_line in (proc.stdout or "").splitlines():
        line = raw_line.rstrip()
        if len(line) < 4:
            continue
        path_part = line[3:].strip()
        if not path_part:
            continue
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1].strip()
        changed.append(path_part.replace("\\", "/"))

    changed = sorted(set(changed))
    return True, changed, ""


def load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def verify_dual_approval(
    repo_root: Path,
    watch_files: List[str],
    approval_file: Path,
    required_approvers: int,
    enforce_always: bool,
    require_git: bool,
) -> Dict[str, Any]:
    violations: List[str] = []
    watch_state, fingerprint = collect_watch_state(repo_root, watch_files)

    git_available, changed_files, git_detail = git_changed_watch_files(repo_root, watch_files)
    approval_required = enforce_always
    if git_available:
        approval_required = approval_required or bool(changed_files)
    elif require_git:
        approval_required = True
        violations.append(f"git status unavailable while require_git=true: {git_detail}")

    approval_data: Dict[str, Any] = {}
    if approval_required:
        if not approval_file.is_file():
            violations.append(f"approval file missing: {approval_file}")
        else:
            approval_data = load_json(approval_file)
            if not approval_data:
                violations.append(f"approval file invalid JSON: {approval_file}")

            approved = approval_data.get("approved")
            if approved is not True:
                violations.append("approval flag must be explicit true")

            approved_at = str(approval_data.get("approved_at", "")).strip()
            if not approved_at:
                violations.append("approval approved_at missing")

            file_fp = str(approval_data.get("change_fingerprint", "")).strip()
            if not file_fp:
                violations.append("approval change_fingerprint missing")
            elif not re.fullmatch(r"[0-9a-f]{64}", file_fp):
                violations.append("approval change_fingerprint must be lowercase sha256 hex")
            elif file_fp != fingerprint:
                violations.append(
                    f"approval fingerprint mismatch: expected={fingerprint} actual={file_fp}"
                )

            approvers_raw = approval_data.get("approvers")
            if not isinstance(approvers_raw, list):
                violations.append("approval approvers missing or invalid")
                approvers = []
            else:
                approvers = []
                seen = set()
                for item in approvers_raw:
                    name = str(item or "").strip()
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    approvers.append(name)
                if len(approvers) < required_approvers:
                    violations.append(
                        f"approval approver count too low: {len(approvers)} < {required_approvers}"
                    )
            approval_data["approvers"] = approvers

    return {
        "passed": len(violations) == 0,
        "threshold": {
            "required_approvers": required_approvers,
            "enforce_always": enforce_always,
            "require_git": require_git,
        },
        "actual": {
            "watch_files": watch_files,
            "watch_state": watch_state,
            "change_fingerprint": fingerprint,
            "git_available": git_available,
            "git_detail": git_detail,
            "changed_watch_files": changed_files,
            "approval_required": approval_required,
            "approval_file": str(approval_file),
            "approvers": approval_data.get("approvers", []),
        },
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate baseline changes with dual approval")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    parser.add_argument(
        "--watch-files",
        default=",".join(DEFAULT_WATCH_FILES),
        help="Comma-separated baseline files that require dual approval when changed",
    )
    parser.add_argument(
        "--approval-file",
        default="prompt-dsl-system/tools/baseline_dual_approval.json",
        help="Approval evidence JSON path",
    )
    parser.add_argument(
        "--required-approvers",
        type=int,
        default=2,
        help="Required unique approver count",
    )
    parser.add_argument(
        "--enforce-always",
        default="false",
        help="true/false; require approval even when watch files are clean",
    )
    parser.add_argument(
        "--require-git",
        default="false",
        help="true/false; fail when git status is unavailable",
    )
    parser.add_argument("--out-json", default="", help="Optional output path for gate report JSON")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    watch_files = parse_watch_files(args.watch_files)
    approval_file = Path(args.approval_file).expanduser()
    if not approval_file.is_absolute():
        approval_file = (repo_root / approval_file).resolve()
    else:
        approval_file = approval_file.resolve()

    if not repo_root.is_dir():
        print(f"[kit_dual_approval] FAIL: invalid repo-root: {repo_root}")
        return EXIT_INVALID_INPUT
    if not watch_files:
        print("[kit_dual_approval] FAIL: watch-files is empty")
        return EXIT_INVALID_INPUT
    if args.required_approvers < 1:
        print("[kit_dual_approval] FAIL: required-approvers must be >= 1")
        return EXIT_INVALID_INPUT

    result = verify_dual_approval(
        repo_root=repo_root,
        watch_files=watch_files,
        approval_file=approval_file,
        required_approvers=int(args.required_approvers),
        enforce_always=parse_bool(args.enforce_always, default=False),
        require_git=parse_bool(args.require_git, default=False),
    )

    out_json_path: Path | None = None
    if args.out_json:
        out_json_path = Path(args.out_json).expanduser().resolve()
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    actual = result["actual"]
    if result["passed"]:
        print(
            "[kit_dual_approval] PASS: "
            f"approval_required={actual['approval_required']} "
            f"changed_watch_files={len(actual['changed_watch_files'])}"
        )
        if out_json_path is not None:
            print(f"[kit_dual_approval] report={out_json_path}")
        return 0

    print("[kit_dual_approval] FAIL")
    for violation in result["violations"]:
        print(f"[kit_dual_approval] violation: {violation}")
    print(f"[kit_dual_approval] change_fingerprint={actual['change_fingerprint']}")
    print(f"[kit_dual_approval] approval_file={actual['approval_file']}")
    if out_json_path is not None:
        print(f"[kit_dual_approval] report={out_json_path}")
    return EXIT_APPROVAL_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
