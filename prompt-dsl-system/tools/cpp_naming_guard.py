#!/usr/bin/env python3
"""C++-aligned naming guard for Java code (heuristic checks)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List

TOOL = "cpp_naming_guard"
TOOL_VERSION = "1.0.0"

BOOLEAN_DECL_RE = re.compile(
    r"\bboolean\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:[=;,)\]])"
)
CONST_DECL_RE = re.compile(
    r"\b(?:public|protected|private)?\s*(?:static\s+final|final\s+static)\s+"
    r"[A-Za-z0-9_<>, ?\[\]]+\s+([A-Za-z_][A-Za-z0-9_]*)\b"
)
UPPER_SNAKE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def is_upper_snake(name: str) -> bool:
    return bool(UPPER_SNAKE_RE.match(name))


def git_changed_java_files(repo_root: Path) -> List[Path]:
    cmd = ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=all"]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        return []
    files: List[Path] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        payload = line[3:].strip()
        if not payload:
            continue
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1].strip()
        if payload.endswith(".java"):
            files.append((repo_root / payload).resolve())
    return files


def list_java_files(root: Path) -> List[Path]:
    return sorted(path for path in root.rglob("*.java") if path.is_file())


def scan_java_file(path: Path) -> List[Dict[str, object]]:
    violations: List[Dict[str, object]] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("*"):
            continue

        for match in BOOLEAN_DECL_RE.finditer(line):
            name = match.group(1)
            if name.startswith(("is", "has", "can")):
                continue
            violations.append(
                {
                    "file": str(path),
                    "line": idx,
                    "rule": "boolean_prefix",
                    "name": name,
                    "message": "boolean naming should start with is_/has_/can_ style prefix",
                }
            )

        for match in CONST_DECL_RE.finditer(line):
            name = match.group(1)
            if is_upper_snake(name):
                continue
            violations.append(
                {
                    "file": str(path),
                    "line": idx,
                    "rule": "constant_upper_snake",
                    "name": name,
                    "message": "constant naming should use UPPER_SNAKE_CASE",
                }
            )

    return violations


def run_guard(repo_root: Path, module_root: Path | None, mode: str) -> dict:
    target_root = module_root or repo_root
    if mode == "changed":
        files = [
            path for path in git_changed_java_files(repo_root)
            if path.is_file() and str(path).startswith(str(target_root))
        ]
    else:
        files = list_java_files(target_root)

    violations: List[Dict[str, object]] = []
    for path in files:
        violations.extend(scan_java_file(path))

    return {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "repo_root": str(repo_root),
        "module_root": str(target_root),
        "mode": mode,
        "summary": {
            "scanned_files": len(files),
            "violations": len(violations),
            "passed": len(violations) == 0,
        },
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run C++-aligned naming checks for Java files.")
    parser.add_argument("--repo-root", required=True, help="Repository root")
    parser.add_argument("--module-root", default="", help="Optional module root override")
    parser.add_argument(
        "--mode",
        choices=("changed", "all"),
        default="changed",
        help="Scan changed Java files or all Java files under module root",
    )
    parser.add_argument(
        "--out-json",
        default="prompt-dsl-system/tools/cpp_naming_report.json",
        help="Output report path",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[{TOOL}] FAIL: invalid repo root: {repo_root}")
        return 2

    module_root = None
    if args.module_root:
        raw = Path(args.module_root)
        module_root = raw if raw.is_absolute() else repo_root / raw
        module_root = module_root.expanduser().resolve()
        if not module_root.is_dir():
            print(f"[{TOOL}] FAIL: invalid module root: {module_root}")
            return 2

    report = run_guard(repo_root=repo_root, module_root=module_root, mode=args.mode)
    out_json = Path(args.out_json)
    if not out_json.is_absolute():
        out_json = repo_root / out_json
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = report.get("summary", {})
    print(
        f"[{TOOL}] scanned_files={summary.get('scanned_files', 0)} "
        f"violations={summary.get('violations', 0)} report={out_json}"
    )
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
