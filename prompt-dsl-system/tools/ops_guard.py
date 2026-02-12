#!/usr/bin/env python3
"""Operational guard for company-domain scope and path safety checks.

Standard-library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

DEFAULT_FORBIDDEN = ["/sys", "/error", "/util", "/vote"]
IGNORE_PATTERNS = [
    "_regression_tmp/",
    ".structure_cache/",
    ".discovered.yaml",
    "testdata/structure_cases/",
    "_tmp_structure_cases/",
    "generated-sources/",
    "generated-test-sources/",
]
REPORT_REL_PATH = "prompt-dsl-system/tools/ops_guard_report.json"
import os


def check_vcs_metadata(repo_root: Path) -> int:
    """Check for .git/ or .svn/ at repo-root.
    Returns 0=found, 1=missing-strict, 2=missing-warn."""
    has_git = (repo_root / ".git").is_dir()
    has_svn = (repo_root / ".svn").is_dir()
    strict = (
        os.environ.get("HONGZHI_GUARD_REQUIRE_VCS", "0") == "1"
        or os.environ.get("HONGZHI_VALIDATE_STRICT", "0") == "1"
    )
    if has_git or has_svn:
        vcs = "git" if has_git else "svn"
        print(f"ops_guard: VCS metadata found ({vcs})")
        return 0
    if strict:
        print("ops_guard: FAIL — no .git/ or .svn/ found (HONGZHI_GUARD_REQUIRE_VCS=1)", file=sys.stderr)
        return 1
    print("ops_guard: [WARN] no .git/ or .svn/ found — VCS metadata missing")
    return 0


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_rel_path(path: str) -> str:
    return path.replace("\\", "/").strip()


def parse_forbidden_paths(raw: str) -> List[str]:
    values = [p.strip() for p in raw.split(",") if p.strip()]
    if not values:
        return list(DEFAULT_FORBIDDEN)
    return [p if p.startswith("/") else f"/{p}" for p in values]


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def is_forbidden(rel_path: str, forbidden_paths: List[str]) -> bool:
    test = "/" + rel_path.lstrip("/")
    for rule in forbidden_paths:
        token = rule.rstrip("/")
        if test == token or test.startswith(token + "/") or (token + "/") in test:
            return True
    return False


def should_ignore(rel_path: str) -> bool:
    """Check if path should be ignored by guard."""
    for pattern in IGNORE_PATTERNS:
        if pattern in rel_path:
            return True
    return False


def candidate_log_files(repo_root: Path) -> List[Path]:
    files = [
        repo_root / "prompt-dsl-system/05_skill_registry/CHANGELOG_CONSTITUTION_UPGRADE.md",
        repo_root / "prompt-dsl-system/05_skill_registry/CONSOLIDATION_CHANGELOG.md",
        repo_root / "prompt-dsl-system/05_skill_registry/REDUNDANCY_REPORT.md",
    ]
    return [f for f in files if f.exists()]


def extract_paths_from_markdown(text: str) -> List[str]:
    candidates = re.findall(r"`([^`]+)`", text)
    paths: List[str] = []
    for c in candidates:
        c_norm = normalize_rel_path(c)
        if c_norm.startswith("prompt-dsl-system/"):
            paths.append(c_norm)
    return paths


def discover_changed_files(repo_root: Path) -> Tuple[List[str], Dict[str, int], List[str]]:
    discovered: Set[str] = set()
    counts: Dict[str, int] = {}
    sources: List[str] = []

    for log_file in candidate_log_files(repo_root):
        sources.append(str(log_file.relative_to(repo_root)).replace("\\", "/"))
        text = log_file.read_text(encoding="utf-8")
        for rel in extract_paths_from_markdown(text):
            discovered.add(rel)
            counts[rel] = counts.get(rel, 0) + 1

    return sorted(discovered), counts, sources


def build_report(
    repo_root: Path,
    allowed_root_input: str,
    forbidden_paths: List[str],
) -> Dict[str, object]:
    allowed_root_path = Path(allowed_root_input)
    if not allowed_root_path.is_absolute():
        allowed_root_path = (repo_root / allowed_root_path).resolve()
    else:
        allowed_root_path = allowed_root_path.resolve()

    changed_files, freq_map, sources = discover_changed_files(repo_root)

    forbidden_hits: List[str] = []
    out_of_scope_hits: List[str] = []

    for rel in changed_files:
        abs_path = (repo_root / rel).resolve()
        if is_forbidden(rel, forbidden_paths):
            forbidden_hits.append(rel)
        if not is_under(abs_path, allowed_root_path):
            out_of_scope_hits.append(rel)

    loop_info: Dict[str, object]
    if not changed_files:
        loop_info = {
            "status": "insufficient_data",
            "message": "需用户提供执行日志",
            "signals": [],
        }
    else:
        signals = []
        for rel, count in sorted(freq_map.items()):
            if count > 3:
                signals.append(
                    {
                        "type": "same_file_referenced_over_3",
                        "file": rel,
                        "count": count,
                    }
                )
        loop_info = {
            "status": "detected" if signals else "not_detected",
            "message": "loop signals from available logs" if signals else "no loop signal in available logs",
            "signals": signals,
        }

    pass_status = not forbidden_hits and not out_of_scope_hits
    suggestions: List[str] = []
    if forbidden_hits:
        suggestions.append("Remove forbidden-path changes and re-run within allowed module root.")
    if out_of_scope_hits:
        suggestions.append("Restrict edits to --allowed-root and regenerate change plan.")
    if not changed_files:
        suggestions.append("Provide change logs or execution logs for stronger loop-risk detection.")

    return {
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "allowed_root": str(allowed_root_path),
        "forbidden_paths": forbidden_paths,
        "change_evidence": {
            "sources": sources,
            "changed_files": changed_files,
        },
        "checks": {
            "forbidden_path_violations": forbidden_hits,
            "out_of_allowed_root_violations": out_of_scope_hits,
            "loop_risk": loop_info,
        },
        "summary": {
            "pass": pass_status,
            "failure_reasons": [
                *(["forbidden_path_violation"] if forbidden_hits else []),
                *(["out_of_allowed_root_violation"] if out_of_scope_hits else []),
            ],
            "suggested_actions": suggestions,
        },
    }


def write_report(repo_root: Path, report: Dict[str, object]) -> Path:
    report_path = repo_root / REPORT_REL_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Company ops guard for scope and forbidden-path checks")
    parser.add_argument("--allowed-root", required=True, help="Allowed module root path (absolute or repo-relative)")
    parser.add_argument("--module-paths", default=None,
                        help="Comma-separated additional module paths (multi-root support)")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    parser.add_argument(
        "--forbidden-paths",
        default=",".join(DEFAULT_FORBIDDEN),
        help="Comma-separated forbidden paths, default: /sys,/error,/util,/vote",
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        print(f"Invalid repo root: {repo_root}", file=sys.stderr)
        return 2

    # VCS metadata check
    vcs_rc = check_vcs_metadata(repo_root)
    if vcs_rc != 0:
        return vcs_rc

    forbidden_paths = parse_forbidden_paths(args.forbidden_paths)
    report = build_report(repo_root, args.allowed_root, forbidden_paths)
    report_path = write_report(repo_root, report)

    status = "PASS" if report["summary"]["pass"] else "FAIL"
    print(f"ops_guard: {status}")
    print(f"report: {report_path}")

    return 0 if report["summary"]["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
