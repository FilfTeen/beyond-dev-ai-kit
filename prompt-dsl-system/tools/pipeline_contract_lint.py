#!/usr/bin/env python3
"""Pipeline Contract Lint — validates pipeline markdown files for contract compliance.

Usage:
    python3 pipeline_contract_lint.py --repo-root <REPO_ROOT> [--fail-on-empty]

Checks:
  1. Every YAML step block must contain allowed_module_root OR module_path
  2. If a step declares read_refs (non-empty), acceptance must mention NavIndex

Exit codes:
  0 = PASS
  1 = FAIL (issues found)
  2 = empty scan with --fail-on-empty, or usage error
"""
import argparse
import os
import pathlib
import re
import sys

PIPELINES_REL = "prompt-dsl-system/04_ai_pipeline_orchestration"
PIPELINE_GLOB = "pipeline_*.md"

YAML_BLOCK_START = re.compile(r"^```yaml\s*$")
YAML_BLOCK_END = re.compile(r"^```\s*$")
MODULE_ROOT_RE = re.compile(r"allowed_module_root:|module_path:")
READ_REFS_RE = re.compile(r"read_refs:\s*\[")
READ_REFS_EMPTY_RE = re.compile(r"read_refs:\s*\[\s*\]")
NAVINDEX_RE = re.compile(r"[Nn]av[Ii]ndex|ref_nav_index", re.IGNORECASE)


def lint_pipeline(path: pathlib.Path, repo_root: pathlib.Path):
    """Lint a single pipeline markdown file."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    rel = path.relative_to(repo_root)
    issues = []
    in_yaml = False
    yaml_start_line = 0
    yaml_lines = []
    step_count = 0

    for i, line in enumerate(lines, 1):
        if not in_yaml and YAML_BLOCK_START.match(line.strip()):
            in_yaml = True
            yaml_start_line = i
            yaml_lines = []
            continue
        if in_yaml and YAML_BLOCK_END.match(line.strip()):
            in_yaml = False
            step_count += 1
            block_text = "\n".join(yaml_lines)
            if not MODULE_ROOT_RE.search(block_text):
                issues.append(f"  {rel} L{yaml_start_line}: missing allowed_module_root/module_path")
            if READ_REFS_RE.search(block_text) and not READ_REFS_EMPTY_RE.search(block_text):
                if not NAVINDEX_RE.search(block_text):
                    issues.append(f"  {rel} L{yaml_start_line}: read_refs non-empty but no NavIndex")
            yaml_lines = []
            continue
        if in_yaml:
            yaml_lines.append(line)

    return issues, step_count


def main():
    parser = argparse.ArgumentParser(description="Pipeline contract lint")
    parser.add_argument("--repo-root", required=True, help="Repository root path")
    parser.add_argument("--fail-on-empty", action="store_true",
                        help="Exit code 2 if no pipelines found (anti-false-green)")
    args = parser.parse_args()

    repo_root = pathlib.Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        print(f"[ERROR] repo-root is not a directory: {args.repo_root}", file=sys.stderr)
        sys.exit(2)

    pipelines_dir = repo_root / PIPELINES_REL
    if not pipelines_dir.is_dir():
        print(f"[pipeline_contract_lint] pipelines dir not found: {PIPELINES_REL}")
        if args.fail_on_empty:
            print("[pipeline_contract_lint] FAIL (--fail-on-empty: repo-root likely wrong)")
            sys.exit(2)
        print("[pipeline_contract_lint] PASS (no pipelines to lint)")
        sys.exit(0)

    pipeline_files = sorted(pipelines_dir.glob(PIPELINE_GLOB))
    if not pipeline_files:
        print("[pipeline_contract_lint] no pipeline_*.md files found")
        if args.fail_on_empty:
            print("[pipeline_contract_lint] FAIL (--fail-on-empty: no pipelines found)")
            sys.exit(2)
        print("[pipeline_contract_lint][WARN] scanned 0 files — verify --repo-root is correct")
        print("[pipeline_contract_lint] PASS")
        sys.exit(0)

    all_issues = []
    total_steps = 0
    for pf in pipeline_files:
        issues, step_count = lint_pipeline(pf, repo_root)
        all_issues.extend(issues)
        total_steps += step_count

    print(f"[pipeline_contract_lint] scanned {len(pipeline_files)} pipeline(s), {total_steps} YAML block(s)")

    # Profile template check: if migration pipeline exists, template must exist
    migration_pipeline = pipelines_dir / "pipeline_module_migration.md"
    profile_template = repo_root / "prompt-dsl-system" / "module_profiles" / "template" / "module_profile.yaml"
    if migration_pipeline.exists() and not profile_template.exists():
        all_issues.append(f"  module_profiles/template/module_profile.yaml missing (required by pipeline_module_migration)")

    # Strict: reject declared profiles with TODO/PLACEHOLDER in allowed_module_root
    strict = (os.environ.get("HONGZHI_VALIDATE_STRICT", "0") == "1")
    profiles_dir = repo_root / "prompt-dsl-system" / "module_profiles"
    if profiles_dir.is_dir():
        for yaml_file in sorted(profiles_dir.rglob("*.yaml")):
            if yaml_file.name.endswith(".discovered.yaml") or "template" in str(yaml_file.relative_to(profiles_dir)):
                continue
            try:
                content = yaml_file.read_text(encoding="utf-8")
                for line in content.splitlines():
                    if "allowed_module_root" in line:
                        val = line.split(":", 1)[1].strip().strip('"').strip("'")
                        if val.upper() in ("TODO", "PLACEHOLDER") or "<" in val:
                            rel_profile = yaml_file.relative_to(repo_root)
                            if strict:
                                all_issues.append(f"  {rel_profile}: allowed_module_root is placeholder '{val}' (strict: FAIL)")
                            else:
                                print(f"[pipeline_contract_lint][WARN] {rel_profile}: allowed_module_root is placeholder '{val}'")
                        break
            except OSError:
                pass

    # Identity hint check: declared profiles should have at least one of backend_package_hint or web_path_hint
    if profiles_dir.is_dir():
        for yaml_file in sorted(profiles_dir.rglob("*.yaml")):
            if yaml_file.name.endswith(".discovered.yaml") or "template" in str(yaml_file.relative_to(profiles_dir)):
                continue
            try:
                content = yaml_file.read_text(encoding="utf-8")
                has_backend = "backend_package_hint" in content and "TODO" not in content.split("backend_package_hint:", 1)[1].split("\n")[0]
                has_web = "web_path_hint" in content and "TODO" not in content.split("web_path_hint:", 1)[1].split("\n")[0]
                if not has_backend and not has_web:
                    rel_profile = yaml_file.relative_to(repo_root)
                    if strict:
                        all_issues.append(f"  {rel_profile}: missing identity hints (backend_package_hint or web_path_hint) (strict: FAIL)")
                    else:
                        print(f"[pipeline_contract_lint][WARN] {rel_profile}: missing identity hints (backend_package_hint or web_path_hint)")
            except (OSError, IndexError):
                pass

    if all_issues:
        print("[pipeline_contract_lint] FAIL")
        for issue in all_issues:
            print(issue)
        sys.exit(1)
    else:
        print("[pipeline_contract_lint] PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
