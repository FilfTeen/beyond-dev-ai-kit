#!/usr/bin/env python3
"""Module Profile Scanner — generates discovered profile (Layer2).

Scans filesystem + grep patterns from declared profile hints,
outputs a discovered.yaml with file_index, navindex, confidence, and fingerprint.

Supports multi-root: reads roots.discovered.yaml (Layer2R) if present,
falls back to --allowed-module-root as single root.
Performance: concurrent scanning, incremental fingerprint.

Standard-library only.
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
                   "**/.git/**", "**/.svn/**", "**/build/**", "**/out/**",
                   "**/_regression_tmp/**", "**/.structure_cache/**",
                   "**/.gradle/**", "**/.mvn/**",
                   "**/generated-sources/**", "**/generated-test-sources/**",
                   "**/test-classes/**", "**/classes/**"]


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


def load_scan_graph(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


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
    parser.add_argument("--allowed-module-root", default=None,
                        help="Repo-relative path to scan (fallback if no roots.discovered.yaml)")
    parser.add_argument("--out", default=None,
                        help="Output path (default: module_profiles/<project>/<module>.discovered.yaml)")
    parser.add_argument("--out-root", "--workspace-root", default=None,
                        help="Output root directory (default: repo-root)")
    parser.add_argument("--scan-graph", default=None,
                        help="Optional scan_graph.json to reuse indexed files and avoid repeated walk")
    parser.add_argument("--read-only", action="store_true",
                        help="No filesystem writes; output to stdout only")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    out_root = Path(args.out_root).resolve() if args.out_root else repo_root
    # Determine scan roots
    roots_discovered_path = repo_root / f"prompt-dsl-system/module_profiles/{args.project_key}/{args.module_key}.roots.discovered.yaml"
    scan_roots = []
    if roots_discovered_path.exists():
        # Parse roots from Layer2R
        text = roots_discovered_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith('- path:'):
                rp = stripped.split(':', 1)[1].strip().strip('"').strip("'")
                rp_full = (repo_root / rp).resolve()
                if rp_full.is_dir():
                    scan_roots.append(rp_full)
        print(f"[scanner] using {len(scan_roots)} roots from {roots_discovered_path.name}")
    # Also check for structure_discovered.yaml roots
    struct_path = repo_root / f"prompt-dsl-system/module_profiles/{args.project_key}/{args.module_key}.structure.discovered.yaml"
    if struct_path.exists() and not scan_roots:
        text = struct_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith('- prefix:'):
                pkg = stripped.split(':', 1)[1].strip().strip('"').strip("'")
                pkg_path = pkg.replace(".", "/")
                # Try common Java source roots
                for java_root in ["src/main/java"]:
                    target = repo_root / java_root / pkg_path
                    if target.is_dir():
                        scan_roots.append(target)
        if scan_roots:
            print(f"[scanner] using {len(scan_roots)} roots from {struct_path.name}")

    if not scan_roots and args.allowed_module_root:
        allowed_root = (repo_root / args.allowed_module_root).resolve()
        if allowed_root.exists() and allowed_root.is_dir():
            scan_roots = [allowed_root]
    if not scan_roots:
        print("FAIL: no scan roots found (provide --allowed-module-root or run module_roots_discover.py first)", file=sys.stderr)
        sys.exit(1)

    # Load declared profile hints
    declared_path = repo_root / f"prompt-dsl-system/module_profiles/{args.project_key}/{args.module_key}.yaml"
    hints = load_declared(declared_path)
    if not declared_path.exists():
        print(f"[scanner] WARN: declared profile not found at {declared_path}, using defaults")

    # Scan all roots with concurrent execution (or reuse scan_graph if provided)
    t_start = time.time()
    merged_file_index = {k: [] for k in list(CATEGORY_PATTERNS.keys()) + ["other"]}
    merged_navindex = []
    all_scanned_files = []

    if args.scan_graph:
        sg = load_scan_graph(Path(args.scan_graph))
        if sg:
            file_index = sg.get("file_index", {}) if isinstance(sg.get("file_index"), dict) else {}
            pooled = []
            for bucket in ("java", "templates", "resources", "other"):
                values = file_index.get(bucket, [])
                if not isinstance(values, list):
                    continue
                for v in values:
                    if isinstance(v, dict):
                        rel = str(v.get("relpath", "") or "")
                    else:
                        rel = str(v)
                    if rel:
                        pooled.append(rel)
            pooled = sorted(set(pooled))
            for rel in pooled:
                cat = categorize_file(rel)
                merged_file_index[cat].append(rel)
                p = repo_root / rel
                if p.is_file():
                    all_scanned_files.append((p, rel))
            # Keep navindex lightweight in scan-graph mode.
            for pattern in hints.get("grep_patterns", []):
                merged_navindex.append({"pattern": pattern, "hit_count": 0, "hits": []})
            print(f"[scanner] using scan graph: {args.scan_graph} (files={len(pooled)})")
        else:
            print(f"[scanner] WARN: invalid --scan-graph file, fallback to filesystem scan: {args.scan_graph}", file=sys.stderr)

    if not all_scanned_files:
        def scan_single_root(sr):
            return scan_files(repo_root, sr, hints)

        with ThreadPoolExecutor(max_workers=min(4, max(1, len(scan_roots)))) as executor:
            future_map = {executor.submit(scan_single_root, sr): sr for sr in scan_roots}
            for future in as_completed(future_map):
                try:
                    fi, ni, af = future.result()
                    for cat in merged_file_index:
                        for f in fi.get(cat, []):
                            if f not in merged_file_index[cat]:
                                merged_file_index[cat].append(f)
                    # Merge navindex (deduplicate by pattern)
                    existing_patterns = {e["pattern"] for e in merged_navindex}
                    for entry in ni:
                        if entry["pattern"] not in existing_patterns:
                            merged_navindex.append(entry)
                            existing_patterns.add(entry["pattern"])
                        else:
                            for me in merged_navindex:
                                if me["pattern"] == entry["pattern"]:
                                    me["hit_count"] += entry["hit_count"]
                                    me["hits"].extend(entry["hits"])
                                    break
                    all_scanned_files.extend(af)
                except Exception as e:
                    print(f"[scanner] WARN: scan error: {e}", file=sys.stderr)

    confidence = compute_confidence(merged_file_index, merged_navindex)
    fingerprint = compute_fingerprint(all_scanned_files)

    # Output
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = out_root / f"prompt-dsl-system/module_profiles/{args.project_key}/{args.module_key}.discovered.yaml"

    if args.read_only:
        # Write to stdout
        import io
        buf = io.StringIO()
        write_discovered(out_path, args.project_key, args.module_key,
                         merged_file_index, merged_navindex, confidence, fingerprint,
                         stream=buf)
        print(buf.getvalue(), end="")
    else:
        write_discovered(out_path, args.project_key, args.module_key,
                         merged_file_index, merged_navindex, confidence, fingerprint)

    total_files = sum(len(v) for v in merged_file_index.values())
    total_hits = sum(e["hit_count"] for e in merged_navindex)
    print(f"[scanner] files indexed: {total_files}, grep hits: {total_hits}, confidence: {confidence}", file=sys.stderr)
    if not args.read_only:
        print(f"[scanner] discovered profile generated: {out_path}", file=sys.stderr)

if __name__ == "__main__":
    main()
