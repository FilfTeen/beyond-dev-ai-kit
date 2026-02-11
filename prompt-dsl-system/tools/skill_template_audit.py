#!/usr/bin/env python3
"""Skill Template Audit — validates skill YAMLs under prompt-dsl-system.

Usage:
    python3 skill_template_audit.py --repo-root <REPO_ROOT> [--scope staging|deployed|all] [--fail-on-empty]

Checks:
  1. No residual {{PLACEHOLDER}} patterns (excl. prompt_template block)
  2. Required YAML Schema fields present (per SKILL_SPEC.md)
  3. Registry ↔ filesystem consistency (skills.json paths exist, status valid)

Exit codes:
  0 = PASS
  1 = FAIL (issues found)
  2 = empty scan with --fail-on-empty, or usage error
"""
import argparse
import json
import pathlib
import re
import sys

REQUIRED_TOP_LEVEL_KEYS = frozenset([
    "name", "description", "version", "domain", "tags",
    "parameters", "prompt_template", "output_contract", "examples",
])

PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")
VALID_STATUSES = {"staging", "deployed", "deprecated"}

SKILLS_REL = "prompt-dsl-system/05_skill_registry/skills"
REGISTRY_REL = "prompt-dsl-system/05_skill_registry/skills.json"
EXCLUDE_DIRS = {"deprecated", "templates"}


def load_registry(repo_root: pathlib.Path):
    """Load skills.json entries."""
    registry_file = repo_root / REGISTRY_REL
    if not registry_file.is_file():
        return []
    try:
        return json.loads(registry_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return []


def check_registry_consistency(entries, repo_root: pathlib.Path):
    """Check registry ↔ filesystem consistency."""
    issues = []
    for entry in entries:
        path = entry.get("path", "")
        name = entry.get("name", "<unknown>")
        status = entry.get("status", "deployed")

        # Status validation
        if status not in VALID_STATUSES:
            issues.append(f"  registry[{name}]: invalid status '{status}' (must be {VALID_STATUSES})")

        # Path existence
        if path:
            full_path = repo_root / path
            if not full_path.is_file():
                issues.append(f"  registry[{name}]: path does not exist: {path}")

    return issues


def find_skill_yamls(repo_root: pathlib.Path, scope: str, entries):
    """Find skill YAMLs, optionally filtered by status scope."""
    skills_dir = repo_root / SKILLS_REL
    if not skills_dir.is_dir():
        return [], {"staging": 0, "deployed": 0}
    status_map = {
        e.get("path", ""): e.get("status", "deployed")
        for e in entries
    }
    results = []
    stats = {"staging": 0, "deployed": 0}
    for p in sorted(skills_dir.rglob("*.yaml")):
        parts = p.relative_to(skills_dir).parts
        if any(part in EXCLUDE_DIRS for part in parts):
            continue
        rel_path = str(p.relative_to(repo_root))
        status = status_map.get(rel_path, "deployed")
        if status in stats:
            stats[status] += 1
        if scope == "all" or status == scope:
            results.append(p)
    return results, stats


def check_placeholders(path: pathlib.Path):
    """Check for residual {{PLACEHOLDER}} patterns, excluding prompt_template block."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_pt = False
    pt_indent = 0
    hits = []
    for line in lines:
        stripped = line.rstrip()
        if not in_pt:
            if stripped.startswith("prompt_template:") and "|" in stripped:
                in_pt = True
                pt_indent = len(line) - len(line.lstrip()) + 2
                continue
        else:
            if stripped and not stripped.startswith("#"):
                ci = len(line) - len(line.lstrip())
                if ci < pt_indent:
                    in_pt = False
                else:
                    continue
            else:
                continue
        if stripped.lstrip().startswith("#"):
            continue
        hits.extend(PLACEHOLDER_RE.findall(stripped))
    return hits


def check_required_keys(path: pathlib.Path):
    """Lightweight top-level key check without PyYAML."""
    text = path.read_text(encoding="utf-8")
    found = set()
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped and not stripped.startswith(" ") and not stripped.startswith("#"):
            key = stripped.split(":")[0].strip()
            if key in REQUIRED_TOP_LEVEL_KEYS:
                found.add(key)
    return sorted(REQUIRED_TOP_LEVEL_KEYS - found)


def main():
    parser = argparse.ArgumentParser(description="Skill template audit")
    parser.add_argument("--repo-root", required=True, help="Repository root path")
    parser.add_argument("--scope", choices=["staging", "deployed", "all"],
                        default="all", help="Filter by status (default: all)")
    parser.add_argument("--fail-on-empty", action="store_true",
                        help="Exit code 2 if no skills found (anti-false-green)")
    args = parser.parse_args()

    repo_root = pathlib.Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        print(f"[ERROR] repo-root is not a directory: {args.repo_root}", file=sys.stderr)
        sys.exit(2)

    # Load registry
    entries = load_registry(repo_root)
    issues = []

    # C: Registry ↔ filesystem consistency
    if entries:
        reg_issues = check_registry_consistency(entries, repo_root)
        issues.extend(reg_issues)

    # Find YAMLs
    skills_dir = repo_root / SKILLS_REL
    if not skills_dir.is_dir():
        print(f"[skill_template_audit] skills dir not found: {SKILLS_REL}")
        if args.fail_on_empty:
            print("[skill_template_audit] FAIL (--fail-on-empty: repo-root likely wrong or no skills dir)")
            sys.exit(2)
        print("[skill_template_audit] PASS (no skills to audit)")
        sys.exit(0)

    yamls, stats = find_skill_yamls(repo_root, args.scope, entries)
    print(f"[skill_template_audit] registry stats: staging={stats['staging']}, deployed={stats['deployed']}")

    if not yamls:
        print(f"[skill_template_audit] scanned 0 skill YAML(s) (scope={args.scope})")
        if args.fail_on_empty:
            print("[skill_template_audit] FAIL (--fail-on-empty: no skills found, repo-root likely wrong)")
            sys.exit(2)
        print("[skill_template_audit][WARN] scanned 0 files — verify --repo-root is correct")
        print("[skill_template_audit] PASS")
        sys.exit(0)

    # Check each YAML
    for yp in yamls:
        rel = yp.relative_to(repo_root)
        placeholders = check_placeholders(yp)
        if placeholders:
            issues.append(f"  {rel}: residual placeholders: {placeholders}")
        missing = check_required_keys(yp)
        if missing:
            issues.append(f"  {rel}: missing required keys: {missing}")

    print(f"[skill_template_audit] scanned {len(yamls)} skill YAML(s) (scope={args.scope})")
    if issues:
        print("[skill_template_audit] FAIL")
        for issue in issues:
            print(issue)
        sys.exit(1)
    else:
        print("[skill_template_audit] PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
