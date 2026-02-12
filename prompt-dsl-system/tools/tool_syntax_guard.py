#!/usr/bin/env python3
"""Syntax gate for Python and shell tooling assets."""

from __future__ import annotations

import argparse
import json
import py_compile
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

EXIT_INVALID_INPUT = 2
EXIT_GUARD_FAIL = 37

DEFAULT_PYTHON_GLOBS = [
    "prompt-dsl-system/tools/*.py",
    "prompt-dsl-system/tools/hongzhi_ai_kit/*.py",
]

DEFAULT_SHELL_FILES = [
    "prompt-dsl-system/tools/run.sh",
    "prompt-dsl-system/tools/golden_path_regression.sh",
    "prompt-dsl-system/tools/contract_samples/replay_contract_samples.sh",
    "prompt-dsl-system/tools/health_runbook.sh",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def collect_python_files(repo_root: Path, globs: List[str]) -> List[Path]:
    found: Dict[str, Path] = {}
    for pattern in globs:
        glob_expr = str(pattern).strip()
        if not glob_expr:
            continue
        for path in sorted(repo_root.glob(glob_expr)):
            if not path.is_file():
                continue
            found[path.resolve().as_posix()] = path.resolve()
    return [found[key] for key in sorted(found.keys())]


def collect_shell_files(repo_root: Path, raw_files: List[str], strict_source_set: bool, violations: List[str]) -> List[Path]:
    files: List[Path] = []
    for rel in raw_files:
        rel_path = str(rel).strip().replace("\\", "/")
        if not rel_path:
            continue
        path = (repo_root / rel_path).resolve()
        if path.is_file():
            files.append(path)
        elif strict_source_set:
            violations.append(f"shell file missing: {rel_path}")
    unique = sorted({p.resolve().as_posix(): p for p in files}.values(), key=lambda p: p.as_posix())
    return unique


def run_guard(
    repo_root: Path,
    python_globs: List[str],
    shell_files: List[str],
    strict_source_set: bool,
) -> Dict[str, Any]:
    violations: List[str] = []
    python_failures: List[Dict[str, str]] = []
    shell_failures: List[Dict[str, str]] = []

    python_files = collect_python_files(repo_root, python_globs)
    if not python_files:
        violations.append("python file set empty")

    for py_file in python_files:
        rel = py_file.relative_to(repo_root).as_posix()
        try:
            py_compile.compile(str(py_file), doraise=True)
        except py_compile.PyCompileError as exc:
            python_failures.append({"path": rel, "error": str(exc)})
            violations.append(f"python syntax error: {rel}")
        except OSError as exc:
            python_failures.append({"path": rel, "error": str(exc)})
            violations.append(f"python read error: {rel}")

    shell_paths = collect_shell_files(repo_root, shell_files, strict_source_set, violations)
    if not shell_paths:
        violations.append("shell file set empty")

    for sh_file in shell_paths:
        rel = sh_file.relative_to(repo_root).as_posix()
        try:
            proc = subprocess.run(
                ["bash", "-n", str(sh_file)],
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            shell_failures.append({"path": rel, "error": str(exc)})
            violations.append(f"shell syntax check failed to execute: {rel}")
            continue
        if proc.returncode != 0:
            stderr = (proc.stderr or proc.stdout or "").strip()
            shell_failures.append({"path": rel, "error": stderr})
            violations.append(f"shell syntax error: {rel}")

    checks_total = len(python_files) + len(shell_paths)
    checks_failed = len(python_failures) + len(shell_failures)
    checks_passed = checks_total - checks_failed
    if checks_passed < 0:
        checks_passed = 0

    report: Dict[str, Any] = {
        "tool": "tool_syntax_guard",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "inputs": {
            "python_globs": python_globs,
            "shell_files": shell_files,
            "strict_source_set": bool(strict_source_set),
        },
        "actual": {
            "python_checked": len(python_files),
            "shell_checked": len(shell_paths),
            "python_failures": python_failures,
            "shell_failures": shell_failures,
        },
        "violations": violations,
        "summary": {
            "checks_total": checks_total,
            "checks_passed": checks_passed,
            "checks_failed": checks_failed,
            "passed": len(violations) == 0,
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Syntax gate for toolkit scripts.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument(
        "--python-glob",
        action="append",
        default=[],
        help="Python glob pattern relative to repo-root. Can be repeated.",
    )
    parser.add_argument(
        "--shell-file",
        action="append",
        default=[],
        help="Shell file path relative to repo-root. Can be repeated.",
    )
    parser.add_argument(
        "--strict-source-set",
        default="true",
        help="true/false; when true, missing configured shell files fail the guard.",
    )
    parser.add_argument("--out-json", default="")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[tool_syntax_guard] FAIL: invalid repo_root: {repo_root}")
        return EXIT_INVALID_INPUT

    python_globs = args.python_glob if args.python_glob else list(DEFAULT_PYTHON_GLOBS)
    shell_files = args.shell_file if args.shell_file else list(DEFAULT_SHELL_FILES)
    strict_source_set = parse_bool(args.strict_source_set, default=True)

    report = run_guard(
        repo_root=repo_root,
        python_globs=python_globs,
        shell_files=shell_files,
        strict_source_set=strict_source_set,
    )

    out_json = str(args.out_json or "").strip()
    if out_json:
        out_path = Path(out_json).expanduser()
        if not out_path.is_absolute():
            out_path = (repo_root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    passed = bool(summary.get("passed", False))
    checks_passed = int(summary.get("checks_passed", 0))
    checks_total = int(summary.get("checks_total", 0))
    violations = report.get("violations", []) if isinstance(report, dict) else []

    if passed:
        print(
            f"[tool_syntax_guard] PASS checks={checks_passed}/{checks_total} "
            f"python={report.get('actual', {}).get('python_checked', 0)} shell={report.get('actual', {}).get('shell_checked', 0)}"
        )
        return 0

    print(f"[tool_syntax_guard] FAIL checks={checks_passed}/{checks_total} violations={len(violations)}")
    for item in violations:
        print(f"  - {item}")
    return EXIT_GUARD_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
