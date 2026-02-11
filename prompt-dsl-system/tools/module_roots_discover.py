#!/usr/bin/env python3
"""Module Roots Discover — auto-discover allowed_module_roots from identity hints.

Reads declared profile (Layer1) identity hints:
  backend_package_hint, web_path_hint, keywords
Scans repo structure and generates roots.discovered.yaml (Layer2R).

Standard-library only.
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCANNER_VERSION = "1.0"

# Generic structural patterns — no project-specific paths
BACKEND_PATTERNS = [
    "src/main/java",           # Maven Java main
    "src/main/kotlin",         # Kotlin
    "src/main/groovy",         # Groovy
]

WEB_PATTERNS = [
    "src/main/resources/templates",
    "src/main/resources/static",
    "webapp",
    "web/src",
]

SQL_PATTERNS = [
    "src/main/resources/mapper",
    "src/main/resources/mybatis",
    "sql",
    "db",
    "scripts/sql",
]

MINIAPP_PATTERNS = [
    "pages",       # uni-app / mp-weixin
    "src/pages",
    "components",
    "static",
]

EXCLUDE_DIRS = frozenset({
    ".git", ".svn", "node_modules", "target", "dist", ".idea",
    "__pycache__", "build", "out", "_regression_tmp", ".structure_cache",
    ".gradle", ".mvn", "generated-sources", "generated-test-sources",
    "test-classes", "classes",
})


def load_identity_hints(declared_path: Path) -> dict:
    """Extract identity hints from declared profile."""
    hints = {"backend_package_hint": "", "web_path_hint": "", "keywords": []}
    if not declared_path.exists():
        return hints
    text = declared_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("backend_package_hint:"):
            hints["backend_package_hint"] = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        elif stripped.startswith("web_path_hint:"):
            hints["web_path_hint"] = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        elif stripped.startswith("keywords:"):
            m = re.search(r'\[(.+)\]', stripped)
            if m:
                hints["keywords"] = [k.strip().strip('"').strip("'") for k in m.group(1).split(",")]
    return hints


def fingerprint_dir(dir_path: Path) -> dict:
    """Compute fingerprint for a directory."""
    file_count = 0
    total_bytes = 0
    latest_mtime = 0.0
    for p in dir_path.rglob("*"):
        if not p.is_file():
            continue
        if any(ex in p.parts for ex in EXCLUDE_DIRS):
            continue
        try:
            st = p.stat()
            file_count += 1
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


def find_backend_roots(repo_root: Path, package_hint: str) -> list:
    """Find backend Java/Kotlin roots matching package hint."""
    if not package_hint:
        return []
    package_path = package_hint.replace(".", "/")
    roots = []
    for pat in BACKEND_PATTERNS:
        base = repo_root / pat
        if not base.exists():
            continue
        # Walk to find the package directory
        target = base / package_path
        if target.is_dir():
            try:
                rel = str(target.relative_to(repo_root)).replace("\\", "/")
            except ValueError:
                continue
            roots.append({"path": rel, "category": "backend_java"})
    # Also search recursively for multi-module projects
    for root, dirs, files in os.walk(str(repo_root)):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        root_p = Path(root)
        for pat in BACKEND_PATTERNS:
            if root_p.name == pat.split("/")[-1] or str(root_p).replace("\\", "/").endswith(pat):
                target = root_p / package_path
                if target.is_dir():
                    try:
                        rel = str(target.relative_to(repo_root)).replace("\\", "/")
                    except ValueError:
                        continue
                    entry = {"path": rel, "category": "backend_java"}
                    if entry not in roots:
                        roots.append(entry)
    return roots


def find_web_roots(repo_root: Path, web_hint: str) -> list:
    """Find web template roots matching web path hint."""
    if not web_hint:
        return []
    roots = []
    for pat in WEB_PATTERNS:
        base = repo_root / pat
        if not base.exists():
            continue
        target = base / web_hint
        if target.is_dir():
            try:
                rel = str(target.relative_to(repo_root)).replace("\\", "/")
            except ValueError:
                continue
            roots.append({"path": rel, "category": "web_template"})
    # Recursive search for multi-module
    for root, dirs, files in os.walk(str(repo_root)):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        root_p = Path(root)
        for pat in WEB_PATTERNS:
            if str(root_p).replace("\\", "/").endswith(pat):
                target = root_p / web_hint
                if target.is_dir():
                    try:
                        rel = str(target.relative_to(repo_root)).replace("\\", "/")
                    except ValueError:
                        continue
                    entry = {"path": rel, "category": "web_template"}
                    if entry not in roots:
                        roots.append(entry)
    return roots


def find_sql_roots(repo_root: Path, module_key: str) -> list:
    """Find SQL/mapper roots related to module."""
    roots = []
    for pat in SQL_PATTERNS:
        base = repo_root / pat
        if not base.exists():
            continue
        # Look for module-specific subdirectory
        target = base / module_key
        if target.is_dir():
            try:
                rel = str(target.relative_to(repo_root)).replace("\\", "/")
            except ValueError:
                continue
            roots.append({"path": rel, "category": "sql"})
    # Recursive for multi-module
    for root, dirs, files in os.walk(str(repo_root)):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        root_p = Path(root)
        for pat in SQL_PATTERNS:
            if str(root_p).replace("\\", "/").endswith(pat):
                target = root_p / module_key
                if target.is_dir():
                    try:
                        rel = str(target.relative_to(repo_root)).replace("\\", "/")
                    except ValueError:
                        continue
                    entry = {"path": rel, "category": "sql"}
                    if entry not in roots:
                        roots.append(entry)
    return roots


def find_miniapp_roots(repo_root: Path, module_key: str) -> list:
    """Find MiniApp/uni-app roots."""
    roots = []
    for root, dirs, files in os.walk(str(repo_root)):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        root_p = Path(root)
        for pat in MINIAPP_PATTERNS:
            if root_p.name == pat.split("/")[-1]:
                target = root_p / module_key
                if target.is_dir():
                    try:
                        rel = str(target.relative_to(repo_root)).replace("\\", "/")
                    except ValueError:
                        continue
                    entry = {"path": rel, "category": "miniapp"}
                    if entry not in roots:
                        roots.append(entry)
    return roots


def write_roots_discovered(out_path: Path, project_key: str, module_key: str,
                            entries: list, repo_root: Path, read_only: bool = False):
    """Write roots.discovered.yaml."""
    lines = [
        "# Auto-generated by module_roots_discover.py — DO NOT EDIT MANUALLY",
        "# Re-run discover to regenerate. Safe to delete.",
        "",
        'profile_kind: "roots_discovered"',
        'profile_version: "1.0"',
        "",
        "identity:",
        f'  project_key: "{project_key}"',
        f'  module_key: "{module_key}"',
        f'  profile_id: "{project_key}/{module_key}"',
        "",
        "roots:",
        f'  generated_at: "{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}"',
        f'  scanner_version: "{SCANNER_VERSION}"',
        f"  entry_count: {len(entries)}",
        "  entries:",
    ]
    for e in entries:
        fp = fingerprint_dir(repo_root / e["path"])
        lines.append(f'    - path: "{e["path"]}"')
        lines.append(f'      category: "{e["category"]}"')
        lines.append(f"      fingerprint:")
        lines.append(f'        file_count: {fp["file_count"]}')
        lines.append(f'        total_bytes: {fp["total_bytes"]}')
        lines.append(f'        latest_mtime: "{fp["latest_mtime"]}"')

    output = "\n".join(lines) + "\n"
    if read_only:
        print(output, end="")
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Auto-discover module roots from identity hints in declared profile")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--project-key", required=True, help="Project identifier")
    parser.add_argument("--module-key", default=None,
                        help="Module identifier (optional — if omitted, uses auto_module_discover)")
    parser.add_argument("--out", default=None,
                        help="Output path (default: module_profiles/<project>/<module>.roots.discovered.yaml)")
    parser.add_argument("--out-root", default=None,
                        help="Output root directory (default: repo-root)")
    parser.add_argument("--read-only", action="store_true",
                        help="No filesystem writes; output to stdout only")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    out_root = Path(args.out_root).resolve() if args.out_root else repo_root

    # If --module-key not given, call auto_module_discover
    module_keys = []
    if not args.module_key:
        print("[roots_discover] --module-key omitted, calling auto_module_discover")
        try:
            from auto_module_discover import find_java_roots, scan_packages, cluster_modules
            java_roots = find_java_roots(repo_root)
            all_pkgs = {}
            for jr in java_roots:
                for pkg, stats in scan_packages(jr).items():
                    if pkg not in all_pkgs:
                        all_pkgs[pkg] = {"files": 0, "controllers": 0, "services": 0, "repositories": 0}
                    for k in ("files", "controllers", "services", "repositories"):
                        all_pkgs[pkg][k] += stats[k]
            candidates = cluster_modules(all_pkgs, [])[:5]
            for c in candidates:
                module_keys.append(c["module_key"])
                print(f"[roots_discover] auto-discovered module: {c['module_key']} (score={c['score']})")
        except ImportError:
            print("[roots_discover] WARN: auto_module_discover.py not available")
    else:
        module_keys = [args.module_key]

    if not module_keys:
        print("[roots_discover] WARN: no module candidates found")
        sys.exit(0)

    for module_key in module_keys:
        # Load declared profile hints
        declared_path = repo_root / f"prompt-dsl-system/module_profiles/{args.project_key}/{module_key}.yaml"
        hints = load_identity_hints(declared_path)
        if not declared_path.exists():
            print(f"[roots_discover] WARN: declared profile not found at {declared_path}, using defaults")

        pkg = hints.get("backend_package_hint", "")
        web = hints.get("web_path_hint", "")

        all_roots = []

        if pkg or web:
            all_roots.extend(find_backend_roots(repo_root, pkg))
            all_roots.extend(find_web_roots(repo_root, web))
        else:
            print("[roots_discover] no identity hints found, using structure_discover fallback")
            try:
                from structure_discover import find_scan_roots, cluster_packages, scan_java_root_incremental
                java_roots, template_roots = find_scan_roots(repo_root)
                java_results = []
                for jr in java_roots:
                    results, _, _, _ = scan_java_root_incremental(jr, repo_root, {})
                    java_results.extend(results)
                clusters = cluster_packages(java_results)
                if clusters:
                    top = clusters[0]
                    pkg_inferred = top["prefix"]
                    pkg_path = pkg_inferred.replace(".", "/")
                    for jr in java_roots:
                        target = jr / pkg_path
                        if target.is_dir():
                            rel = str(target.relative_to(repo_root)).replace("\\", "/")
                            all_roots.append({"path": rel, "category": "backend_java"})
                    print(f"[roots_discover] structure fallback inferred: {pkg_inferred}")
                for tr in template_roots:
                    target = tr / module_key
                    if target.is_dir():
                        rel = str(target.relative_to(repo_root)).replace("\\", "/")
                        all_roots.append({"path": rel, "category": "web_template"})
            except ImportError:
                print("[roots_discover] WARN: structure_discover.py not available, skipping fallback")

        all_roots.extend(find_sql_roots(repo_root, module_key))
        all_roots.extend(find_miniapp_roots(repo_root, module_key))

        # Deduplicate
        seen = set()
        unique_roots = []
        for r in all_roots:
            key = r["path"]
            if key not in seen:
                seen.add(key)
                unique_roots.append(r)

        # Output
        if args.out:
            out_path = Path(args.out)
        else:
            out_path = out_root / f"prompt-dsl-system/module_profiles/{args.project_key}/{module_key}.roots.discovered.yaml"

        write_roots_discovered(out_path, args.project_key, module_key, unique_roots, repo_root,
                               read_only=args.read_only)

        print(f"[roots_discover] [{module_key}] roots discovered: {len(unique_roots)}", file=sys.stderr)
        for r in unique_roots:
            print(f"  [{r['category']}] {r['path']}", file=sys.stderr)
        if not args.read_only:
            print(f"[roots_discover] output: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
