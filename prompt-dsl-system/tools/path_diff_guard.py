#!/usr/bin/env python3
"""Path Diff Guard for hongzhi prompt-dsl-system tools.

Standard-library only implementation.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_IGNORE_PATTERNS = [
    "**/target/**",
    "**/node_modules/**",
    "**/.DS_Store",
    "**/*.log",
]

DEFAULT_GUARDRAILS = {
    "company_scope": {"name": "hongzhi-work-dev", "enabled": True},
    "forbidden_path_patterns": [
        "**/sys/**",
        "**/error/**",
        "**/util/**",
        "**/vote/**",
        "**/.git/**",
        "**/target/**",
        "**/node_modules/**",
    ],
    "ignore_path_patterns": DEFAULT_IGNORE_PATTERNS,
    "allowlist_rules": {
        "allow_prompt_dsl_system": True,
        "require_module_path_for_project_changes": True,
    },
    "enforcement": {
        "on_violation": "fail-fast",
        "exit_code": 2,
        "report_path": "prompt-dsl-system/tools/guard_report.json",
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_scalar(value: str) -> Any:
    raw = value.strip()
    if raw == "":
        return ""
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        return raw[1:-1]
    low = raw.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none", "~"):
        return None
    if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
        try:
            return int(raw)
        except ValueError:
            return raw
    return raw


def normalize_rel(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def run_cmd(cmd: List[str], cwd: Path) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def load_guardrails(path: Path) -> Tuple[Dict[str, Any], List[str], List[str]]:
    cfg = json.loads(json.dumps(DEFAULT_GUARDRAILS))
    warnings: List[str] = []
    errors: List[str] = []

    if not path.exists():
        errors.append(f"Guardrails file not found: {path}")
        return cfg, warnings, errors

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(f"Failed to read guardrails file: {exc}")
        return cfg, warnings, errors

    current_section: Optional[str] = None

    for line_no, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" "))

        if indent == 0:
            if ":" not in stripped:
                warnings.append(f"Ignoring invalid top-level line {line_no}: {stripped}")
                current_section = None
                continue
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value == "":
                current_section = key
                if key in ("forbidden_path_patterns", "ignore_path_patterns"):
                    cfg[key] = []
                elif key in ("allowlist_rules", "enforcement", "company_scope"):
                    cfg[key] = {}
                elif key not in cfg:
                    cfg[key] = []
            else:
                cfg[key] = parse_scalar(value)
                current_section = None
            continue

        if indent == 2 and current_section is not None:
            if stripped.startswith("- "):
                arr = cfg.setdefault(current_section, [])
                if not isinstance(arr, list):
                    errors.append(f"Section {current_section} must be a list (line {line_no})")
                    continue
                arr.append(parse_scalar(stripped[2:].strip()))
                continue

            if ":" in stripped:
                parent = cfg.setdefault(current_section, {})
                if not isinstance(parent, dict):
                    errors.append(f"Section {current_section} must be a map (line {line_no})")
                    continue
                key, value = stripped.split(":", 1)
                parent[key.strip()] = parse_scalar(value.strip())
                continue

        warnings.append(f"Ignoring unsupported guardrails line {line_no}: {stripped}")

    return cfg, warnings, errors


def parse_changed_files_env() -> List[str]:
    raw = os.environ.get("HONGZHI_GUARD_CHANGED_FILES", "").strip()
    if not raw:
        return []

    files: List[str] = []
    for chunk in raw.replace("\n", ",").split(","):
        rel = normalize_rel(chunk.strip())
        if rel:
            files.append(rel)

    return sorted(set(files))


def parse_git_status_porcelain(output: str) -> List[str]:
    files: List[str] = []

    for line in output.splitlines():
        if not line.strip() or len(line) < 3:
            continue

        status = line[:2]
        if status == "!!":
            continue

        entry = line[3:].strip()
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1].strip()

        if entry.startswith('"') and entry.endswith('"') and len(entry) >= 2:
            entry = entry[1:-1]

        rel = normalize_rel(entry)
        if rel:
            files.append(rel)

    return sorted(set(files))


def git_changed_files(
    repo_root: Path,
    base: Optional[str],
    head: Optional[str],
    since_last_commit: bool,
) -> Tuple[List[str], List[str], List[str]]:
    warnings: List[str] = []
    errors: List[str] = []

    if (base and not head) or (head and not base):
        errors.append("Both --base and --head must be provided together for git diff mode")
        return [], warnings, errors

    if base and head:
        code, out, err = run_cmd(["git", "diff", "--name-only", base, head], repo_root)
        if code != 0:
            errors.append(f"git diff failed: {err.strip()}")
            return [], warnings, errors
        files = [normalize_rel(x.strip()) for x in out.splitlines() if x.strip()]
        return sorted(set(files)), warnings, errors

    if since_last_commit:
        code, out, err = run_cmd(["git", "diff", "--name-only", "HEAD"], repo_root)
        if code != 0:
            errors.append(f"git diff HEAD failed: {err.strip()}")
            return [], warnings, errors
        files = [normalize_rel(x.strip()) for x in out.splitlines() if x.strip()]
        return sorted(set(files)), warnings, errors

    code, out, err = run_cmd(["git", "status", "--porcelain"], repo_root)
    if code != 0:
        errors.append(f"git status --porcelain failed: {err.strip()}")
        return [], warnings, errors

    return parse_git_status_porcelain(out), warnings, errors


def svn_changed_files(repo_root: Path) -> Tuple[List[str], List[str], List[str]]:
    warnings: List[str] = []
    errors: List[str] = []

    code, out, err = run_cmd(["svn", "status"], repo_root)
    # svn externals warning should not block
    if code != 0 and err:
        err_low = err.lower()
        if "externals" in err_low or "warning" in err_low:
            warnings.append(f"svn status warning: {err.strip()}")
        else:
            errors.append(f"svn status failed: {err.strip()}")
            return [], warnings, errors

    files: List[str] = []
    for line in out.splitlines():
        if not line.strip() or len(line) < 9:
            continue

        status = line[0]
        if status == "X":
            warnings.append("Ignored svn external reference entry")
            continue

        if status in {"M", "A", "D", "R", "?", "!", "~", "C"}:
            rel = normalize_rel(line[8:].strip())
            if rel:
                files.append(rel)

    return sorted(set(files)), warnings, errors


def detect_vcs_changed_files(
    repo_root: Path,
    base: Optional[str],
    head: Optional[str],
    since_last_commit: bool,
) -> Tuple[str, List[str], bool, List[str], List[str]]:
    warnings: List[str] = []
    errors: List[str] = []

    synthetic = parse_changed_files_env()
    if synthetic:
        return "synthetic", synthetic, False, warnings, errors

    if (repo_root / ".git").exists():
        files, warns, errs = git_changed_files(repo_root, base, head, since_last_commit)
        warnings.extend(warns)
        errors.extend(errs)
        return "git", files, False, warnings, errors

    if (repo_root / ".svn").exists():
        files, warns, errs = svn_changed_files(repo_root)
        warnings.extend(warns)
        errors.extend(errs)
        return "svn", files, False, warnings, errors

    warnings.append("No git/svn metadata found; guard runs in non-blocking mode.")
    return "none", [], True, warnings, errors


def path_matches_pattern(rel_path: str, pattern: str) -> bool:
    rel = normalize_rel(rel_path)
    pat = pattern.strip()
    if not pat:
        return False

    p = PurePosixPath(rel)
    if p.match(pat):
        return True

    if pat.startswith("**/") and pat.endswith("/**"):
        token = pat[3:-3].strip("/")
        if token:
            return f"/{token}/" in f"/{rel.strip('/')}/"

    return False


def normalize_module_path(
    module_path: Optional[str], repo_root: Path
) -> Tuple[Optional[Path], Optional[str], Optional[str]]:
    if not module_path:
        return None, None, None

    candidate = Path(module_path)
    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if not candidate.exists() or not candidate.is_dir():
        return None, None, f"module_path is not an existing directory: {module_path}"

    try:
        rel = normalize_rel(str(candidate.relative_to(repo_root.resolve())))
    except ValueError:
        return None, None, f"module_path must be inside repo-root: {module_path}"

    if rel == "":
        rel = "."

    return candidate, rel, None


def is_allowed_by_module(rel_path: str, module_rel: str) -> bool:
    if module_rel == ".":
        return True
    return rel_path == module_rel or rel_path.startswith(module_rel + "/")


def unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def evaluate_changes(
    changed_files: List[str],
    module_rel: Optional[str],
    cfg: Dict[str, Any],
) -> Tuple[List[str], List[Dict[str, str]], List[str], Dict[str, Any]]:
    forbidden_patterns_raw = cfg.get("forbidden_path_patterns", [])
    forbidden_patterns = [p for p in forbidden_patterns_raw if isinstance(p, str)]
    if not forbidden_patterns:
        forbidden_patterns = list(DEFAULT_GUARDRAILS["forbidden_path_patterns"])

    ignore_patterns_raw = cfg.get("ignore_path_patterns", DEFAULT_IGNORE_PATTERNS)
    ignore_patterns = [p for p in ignore_patterns_raw if isinstance(p, str)]
    if not ignore_patterns:
        ignore_patterns = list(DEFAULT_IGNORE_PATTERNS)

    allowlist_rules = cfg.get("allowlist_rules", {})
    if not isinstance(allowlist_rules, dict):
        allowlist_rules = {}

    allow_prompt_dsl = bool(allowlist_rules.get("allow_prompt_dsl_system", True))
    require_module = bool(allowlist_rules.get("require_module_path_for_project_changes", True))

    filtered_changed: List[str] = []
    ignored_files: List[str] = []
    violations: List[Dict[str, str]] = []

    for rel in changed_files:
        rel_norm = normalize_rel(rel)
        if not rel_norm:
            continue

        forbidden_hit = None
        for pattern in forbidden_patterns:
            if path_matches_pattern(rel_norm, pattern):
                forbidden_hit = pattern
                break

        if forbidden_hit is not None:
            violations.append(
                {
                    "file": rel_norm,
                    "rule": "forbidden_path_patterns",
                    "type": "forbidden",
                    "reason": f"matched forbidden pattern: {forbidden_hit}",
                    "suggestion": "Revert forbidden changes or move work inside allowed module boundary.",
                }
            )
            filtered_changed.append(rel_norm)
            continue

        ignore_hit = None
        for pattern in ignore_patterns:
            if path_matches_pattern(rel_norm, pattern):
                ignore_hit = pattern
                break

        if ignore_hit is not None:
            ignored_files.append(rel_norm)
            continue

        allowed = False
        if allow_prompt_dsl and rel_norm.startswith("prompt-dsl-system/"):
            allowed = True

        if module_rel is not None:
            if is_allowed_by_module(rel_norm, module_rel):
                allowed = True
        elif require_module and not rel_norm.startswith("prompt-dsl-system/"):
            violations.append(
                {
                    "file": rel_norm,
                    "rule": "module_path_required",
                    "type": "missing_module_path",
                    "reason": "module_path missing while project changes are present",
                    "suggestion": "Provide -m/--module-path to define module boundary.",
                }
            )
            filtered_changed.append(rel_norm)
            continue

        if not allowed:
            violations.append(
                {
                    "file": rel_norm,
                    "rule": "out_of_allowed_scope",
                    "type": "outside_module",
                    "reason": "changed file is outside module_path/** and prompt-dsl-system/**",
                    "suggestion": "Move change under module_path/** or revert out-of-scope edits.",
                }
            )

        filtered_changed.append(rel_norm)

    effective_rules = {
        "forbidden_patterns": forbidden_patterns,
        "allow_prompt_dsl_system": allow_prompt_dsl,
        "require_module_path_for_project_changes": require_module,
    }

    return unique_keep_order(filtered_changed), violations, unique_keep_order(ignored_files), effective_rules


def build_suggestions(violations: List[Dict[str, str]], module_rel: Optional[str]) -> List[str]:
    suggestions: List[str] = []
    rules = [v.get("rule", "") for v in violations]

    if "module_path_required" in rules:
        suggestions.append("传入 -m/--module-path 指定模块边界")
    if "forbidden_path_patterns" in rules:
        suggestions.append("回退命中 forbidden_path_patterns 的改动")
    if "out_of_allowed_scope" in rules:
        suggestions.append("回退越界文件或将改动迁回 module_path/**")

    if not violations and module_rel is None:
        suggestions.append("建议传入 -m/--module-path 以启用更精确边界检查")

    return unique_keep_order(suggestions)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Path Diff Guard for hongzhi runner")
    parser.add_argument("--repo-root", required=True, help="Repository root path")
    parser.add_argument("--module-path", help="Optional module boundary path")
    parser.add_argument("--module-path-source", default="none", choices=["cli", "pipeline", "derived", "none"])
    parser.add_argument("--base", help="Optional VCS base ref")
    parser.add_argument("--head", help="Optional VCS head ref")
    parser.add_argument("--mode", required=True, choices=["validate", "run", "debug-guard"], help="Runner mode")
    parser.add_argument("--since-last-commit", action="store_true", help="Use git diff --name-only HEAD")
    parser.add_argument("--advisory", action="store_true", help="Do not block on violations; exit code is always 0")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        print(f"Invalid repo root: {repo_root}", file=sys.stderr)
        return 2

    guardrails_path = repo_root / "prompt-dsl-system" / "tools" / "guardrails.yaml"
    cfg, warnings, errors = load_guardrails(guardrails_path)

    enforcement = cfg.get("enforcement", {})
    if not isinstance(enforcement, dict):
        enforcement = {}
    fail_exit_code = int(enforcement.get("exit_code", 2) or 2)
    report_rel_path = str(enforcement.get("report_path", "prompt-dsl-system/tools/guard_report.json"))
    report_path = (repo_root / report_rel_path).resolve()

    module_abs, module_rel, module_err = normalize_module_path(args.module_path, repo_root)
    if module_err:
        errors.append(module_err)

    vcs, changed_files_raw, unsupported_vcs, vcs_warnings, vcs_errors = detect_vcs_changed_files(
        repo_root, args.base, args.head, args.since_last_commit
    )
    warnings.extend(vcs_warnings)
    errors.extend(vcs_errors)

    filtered_changed: List[str] = []
    violations: List[Dict[str, str]] = []
    ignored_files: List[str] = []
    decision = "pass"
    exit_code = 0
    decision_reason = "all checks passed"
    effective_rules = {
        "forbidden_patterns": cfg.get("forbidden_path_patterns", DEFAULT_GUARDRAILS["forbidden_path_patterns"]),
        "allow_prompt_dsl_system": True,
        "require_module_path_for_project_changes": True,
    }

    if errors:
        decision = "fail"
        exit_code = 2
        decision_reason = "guard configuration or arguments are invalid"
    elif unsupported_vcs:
        # Strict mode: if VCS required but missing, FAIL
        strict = (os.environ.get("HONGZHI_GUARD_REQUIRE_VCS", "0") == "1" or
                  os.environ.get("HONGZHI_VALIDATE_STRICT", "0") == "1")
        if strict:
            decision = "fail"
            exit_code = fail_exit_code
            decision_reason = "strict mode: no VCS metadata (.git/.svn) found"
            errors.append("No git/svn metadata found; strict mode requires VCS presence.")
        else:
            decision = "pass"
            exit_code = 0
            decision_reason = "vcs unsupported; guard ran in non-blocking mode"
    else:
        filtered_changed, violations, ignored_files, effective_rules = evaluate_changes(changed_files_raw, module_rel, cfg)
        if violations:
            decision = "fail"
            exit_code = fail_exit_code
            first = violations[0]
            decision_reason = f"violation: {first.get('rule', 'unknown')} ({first.get('file', '-')})"
        elif not filtered_changed:
            decision_reason = "no changed files after filtering"
        else:
            decision_reason = "all changed files are within allowed scope"

    suggestions = build_suggestions(violations, module_rel)

    effective_allowlist_prefixes: List[str] = []
    if bool(effective_rules.get("allow_prompt_dsl_system", True)):
        effective_allowlist_prefixes.append("prompt-dsl-system/")
    if module_rel is not None:
        if module_rel == ".":
            effective_allowlist_prefixes.append("./")
        else:
            effective_allowlist_prefixes.append(module_rel.rstrip("/") + "/")
    effective_allowlist_prefixes = unique_keep_order(effective_allowlist_prefixes)

    if args.advisory and decision == "fail":
        warnings.append("advisory mode enabled: violations detected but not blocking")
        exit_code = 0

    report = {
        "timestamp": now_iso(),
        "repo_root": str(repo_root),
        "mode": args.mode,
        "advisory": bool(args.advisory),
        "vcs": vcs,
        "unsupported_vcs": unsupported_vcs,
        "module_path": str(module_abs) if module_abs else None,
        "module_path_normalized": module_rel,
        "module_path_source": args.module_path_source,
        "effective_allowlist_prefixes": effective_allowlist_prefixes,
        "changed_files": filtered_changed,
        "ignored_files": ignored_files,
        "ignore_patterns": cfg.get("ignore_path_patterns", DEFAULT_IGNORE_PATTERNS),
        "effective_rules": effective_rules,
        "warnings": warnings,
        "errors": errors,
        "violations": violations,
        "decision": decision,
        "decision_reason": decision_reason,
        "suggestions": suggestions,
        "exit_code": exit_code,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if errors:
        for err in errors:
            print(f"[guard][error] {err}", file=sys.stderr)

    if warnings:
        for warn in warnings:
            print(f"[guard][warn] {warn}", file=sys.stderr)

    if violations:
        for item in violations:
            print(
                f"[guard][violation] {item['file']} | {item['rule']} | {item['reason']}",
                file=sys.stderr,
            )
        if args.advisory:
            print("[guard][warn] advisory=true; violations reported without blocking", file=sys.stderr)

    print(f"[guard] decision={decision} report={report_rel_path}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
