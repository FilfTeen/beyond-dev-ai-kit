#!/usr/bin/env python3
"""Module Profile Scanner — generates discovered profile (Layer2).

Scans filesystem + grep patterns from declared profile hints,
outputs a discovered.yaml with file_index, navindex, and confidence.

Standard-library only.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


SCANNER_VERSION = "1.0"

CATEGORY_PATTERNS = {
    "controller": [r"[Cc]ontroller"],
    "service": [r"[Ss]ervice(?!.*[Tt]est)"],
    "mapper": [r"[Mm]apper", r"[Dd]ao"],
    "sql_script": [r"\.sql$"],
    "ui_pages": [r"\.html$", r"\.vue$", r"\.jsx?$"],
    "workflow_activiti": [r"\.bpmn", r"[Pp]rocess", r"[Ww]orkflow"],
    "dto": [r"[Dd]to"],
    "vo": [r"[Vv]o(?:\.java)?$"],
    "config": [r"\.properties$", r"\.ya?ml$", r"application"],
    "repository": [r"[Rr]epository"],
}

DEFAULT_INCLUDE = ["**/*.java", "**/*.xml", "**/*.html", "**/*.sql",
                   "**/*.vue", "**/*.bpmn", "**/*.properties", "**/*.yml", "**/*.yaml"]
DEFAULT_EXCLUDE = ["**/node_modules/**", "**/target/**", "**/dist/**",
                   "**/.git/**", "**/.svn/**"]


def load_declared(path: Path) -> dict:
    """Minimal YAML-like loader for declared profile (key: value pairs)."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    # Extract grep_patterns list
    patterns = []
    in_patterns = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("grep_patterns:"):
            # Try inline list: grep_patterns: ["A", "B"]
            m = re.search(r'\[(.+)\]', stripped)
            if m:
                patterns = [p.strip().strip('"').strip("'") for p in m.group(1).split(",")]
            else:
                in_patterns = True
            continue
        if in_patterns:
            if stripped.startswith("- "):
                patterns.append(stripped[2:].strip().strip('"').strip("'"))
            else:
                in_patterns = False

    # Extract include/exclude globs
    include_globs = []
    exclude_globs = []
    in_inc = False
    in_exc = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("include_globs:"):
            m = re.search(r'\[(.+)\]', stripped)
            if m:
                include_globs = [p.strip().strip('"').strip("'") for p in m.group(1).split(",")]
            else:
                in_inc = True
                in_exc = False
            continue
        if stripped.startswith("exclude_globs:"):
            m = re.search(r'\[(.+)\]', stripped)
            if m:
                exclude_globs = [p.strip().strip('"').strip("'") for p in m.group(1).split(",")]
            else:
                in_exc = True
                in_inc = False
            continue
        if in_inc and stripped.startswith("- "):
            include_globs.append(stripped[2:].strip().strip('"').strip("'"))
        elif in_exc and stripped.startswith("- "):
            exclude_globs.append(stripped[2:].strip().strip('"').strip("'"))
        elif not stripped.startswith("- "):
            in_inc = False
            in_exc = False

    return {
        "grep_patterns": patterns or ["TODO"],
        "include_globs": include_globs or DEFAULT_INCLUDE,
        "exclude_globs": exclude_globs or DEFAULT_EXCLUDE,
    }


def should_exclude(rel_path: str, excludes: list) -> bool:
    for exc in excludes:
        exc_clean = exc.replace("**/", "").replace("/**", "")
        if exc_clean.strip("*") and exc_clean.strip("*") in rel_path:
            return True
    return False


def categorize_file(rel_path: str) -> str:
    for cat, pats in CATEGORY_PATTERNS.items():
        for pat in pats:
            if re.search(pat, rel_path):
                return cat
    return "other"


def scan_files(root: Path, allowed_root: Path, hints: dict) -> tuple:
    """Scan filesystem and return (file_index, navindex)."""
    file_index = {k: [] for k in list(CATEGORY_PATTERNS.keys()) + ["other"]}
    navindex = []

    # Collect files
    all_files = []
    for p in sorted(allowed_root.rglob("*")):
        if not p.is_file():
            continue
        try:
            rel = str(p.relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
        if should_exclude(rel, hints.get("exclude_globs", DEFAULT_EXCLUDE)):
            continue
        # Check include patterns (by extension)
        inc_globs = hints.get("include_globs", DEFAULT_INCLUDE)
        ext_match = False
        for ig in inc_globs:
            ext = ig.replace("**/*", "").replace("*", "")
            if ext and rel.endswith(ext):
                ext_match = True
                break
        if not ext_match and inc_globs:
            continue
        all_files.append((p, rel))

    # Categorize
    for p, rel in all_files:
        cat = categorize_file(rel)
        file_index[cat].append(rel)

    # Grep patterns
    grep_patterns = hints.get("grep_patterns", [])
    for pattern in grep_patterns:
        if pattern == "TODO":
            continue
        hits = []
        for p, rel in all_files:
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if pattern in line:
                    hits.append({
                        "file": rel,
                        "line": i,
                        "snippet": line.strip()[:120],
                    })
                    if len(hits) >= 50:  # cap per pattern
                        break
            if len(hits) >= 50:
                break
        navindex.append({"pattern": pattern, "hit_count": len(hits), "hits": hits[:20]})

    return file_index, navindex, all_files


def compute_confidence(file_index: dict, navindex: list) -> str:
    total_files = sum(len(v) for v in file_index.values())
    total_hits = sum(e["hit_count"] for e in navindex)
    if total_files >= 10 and total_hits >= 20:
        return "high"
    if total_files >= 3 or total_hits >= 5:
        return "medium"
    return "low"


def format_yaml_list(items: list, indent: int = 6) -> str:
    if not items:
        return " []"
    prefix = " " * indent
    return "\n" + "\n".join(f"{prefix}- \"{item}\"" for item in items)


def compute_fingerprint(all_files: list) -> dict:
    """Compute fingerprint from scanned files."""
    file_count = len(all_files)
    total_bytes = 0
    latest_mtime = 0.0
    for p, rel in all_files:
        try:
            st = p.stat()
            total_bytes += st.st_size
            if st.st_mtime > latest_mtime:
                latest_mtime = st.st_mtime
        except OSError:
            pass
    return {
        "file_count": file_count,
        "total_bytes": total_bytes,
        "latest_mtime": datetime.fromtimestamp(latest_mtime, tz=timezone.utc).replace(microsecond=0).isoformat() if latest_mtime > 0 else "unknown",
    }


def write_discovered(out_path: Path, project_key: str, module_key: str,
                     file_index: dict, navindex: list, confidence: str,
                     fingerprint: dict):
    lines = [
        "# Auto-generated by module_profile_scanner.py — DO NOT EDIT MANUALLY",
        "# Re-run scanner to regenerate. Safe to delete.",
        "",
        'profile_kind: "discovered"',
        'profile_version: "1.0"',
        "",
        "identity:",
        f'  project_key: "{project_key}"',
        f'  module_key: "{module_key}"',
        f'  profile_id: "{project_key}/{module_key}"',
        "",
        "discovery:",
        f'  generated_at: "{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}"',
        f'  scanner_version: "{SCANNER_VERSION}"',
        f'  confidence: "{confidence}"',
        "",
        "  fingerprint:",
        f'    file_count: {fingerprint["file_count"]}',
        f'    total_bytes: {fingerprint["total_bytes"]}',
        f'    latest_mtime: "{fingerprint["latest_mtime"]}"',
        "",
        "  file_index:",
    ]
    for cat in list(CATEGORY_PATTERNS.keys()) + ["other"]:
        files = file_index.get(cat, [])
        lines.append(f"    {cat}:{format_yaml_list(files)}")

    lines.append("")
    lines.append("  navindex:")
    for entry in navindex:
        lines.append(f'    - pattern: "{entry["pattern"]}"')
        lines.append(f'      hit_count: {entry["hit_count"]}')
        lines.append("      hits:")
        for h in entry["hits"][:10]:
            snippet = h["snippet"].replace('"', '\\"')
            lines.append(f'        - file: "{h["file"]}"')
            lines.append(f'          line: {h["line"]}')
            lines.append(f'          snippet: "{snippet}"')

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Generate discovered module profile (Layer2) by scanning filesystem")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--project-key", required=True, help="Project identifier")
    parser.add_argument("--module-key", required=True, help="Module identifier")
    parser.add_argument("--allowed-module-root", required=True,
                        help="Repo-relative path to scan (e.g. src/main/java/com/indihx/notice)")
    parser.add_argument("--out", default=None,
                        help="Output path (default: module_profiles/<project>/<module>.discovered.yaml)")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    allowed_root = (repo_root / args.allowed_module_root).resolve()

    if not allowed_root.exists() or not allowed_root.is_dir():
        print(f"FAIL: allowed-module-root does not exist: {allowed_root}", file=sys.stderr)
        sys.exit(1)

    # Load declared profile hints
    declared_path = repo_root / f"prompt-dsl-system/module_profiles/{args.project_key}/{args.module_key}.yaml"
    hints = load_declared(declared_path)
    if not declared_path.exists():
        print(f"[scanner] WARN: declared profile not found at {declared_path}, using defaults")

    # Scan
    file_index, navindex, all_files = scan_files(repo_root, allowed_root, hints)
    confidence = compute_confidence(file_index, navindex)
    fingerprint = compute_fingerprint(all_files)

    # Output
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = repo_root / f"prompt-dsl-system/module_profiles/{args.project_key}/{args.module_key}.discovered.yaml"

    write_discovered(out_path, args.project_key, args.module_key,
                     file_index, navindex, confidence, fingerprint)

    total_files = sum(len(v) for v in file_index.values())
    total_hits = sum(e["hit_count"] for e in navindex)
    print(f"[scanner] discovered profile generated: {out_path}")
    print(f"[scanner] files indexed: {total_files}, grep hits: {total_hits}, confidence: {confidence}")
    print(f"[scanner] fingerprint: file_count={fingerprint['file_count']}, total_bytes={fingerprint['total_bytes']}, latest_mtime={fingerprint['latest_mtime']}")


if __name__ == "__main__":
    main()
