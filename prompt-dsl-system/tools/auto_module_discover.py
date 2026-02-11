#!/usr/bin/env python3
"""Auto Module Discover — identify modules in a repo without specifying --module-key.

Scans all Java packages, clusters them by prefix, and returns top-k module candidates
with confidence scores. No identity hints required.

Standard-library only. Python 3.9+ compatible.
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

# Shared ignore list — canonical for all discovery tools
IGNORE_DIRS = frozenset({
    ".git", ".svn", "node_modules", "target", "dist", ".idea",
    "__pycache__", "build", "out", "_regression_tmp", ".structure_cache",
    ".gradle", ".mvn", "generated-sources", "generated-test-sources",
    "test-classes", "classes",
})

CONTROLLER_RE = re.compile(r'@(Rest)?Controller|@RequestMapping|@GetMapping|@PostMapping')
SERVICE_RE = re.compile(r'@Service|class\s+\w+Service\w*')
REPOSITORY_RE = re.compile(r'@Repository|@Mapper|interface\s+\w+Mapper|interface\s+\w+Repository')


def find_java_roots(repo_root: Path) -> list:
    """Find all src/main/java directories."""
    roots = []
    for root, dirs, _files in os.walk(str(repo_root)):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        rp = Path(root)
        rel = str(rp.relative_to(repo_root)).replace("\\", "/")
        if rel.endswith("src/main/java") or rel == "src/main/java":
            roots.append(rp)
    return roots


def scan_packages(java_root: Path) -> dict:
    """Scan all .java files under a root and collect package → class info."""
    pkg_data = {}
    for p in java_root.rglob("*.java"):
        if any(ex in p.parts for ex in IGNORE_DIRS):
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        pkg_match = re.search(r'^package\s+([\w.]+)\s*;', content, re.MULTILINE)
        if not pkg_match:
            continue
        pkg = pkg_match.group(1)
        if pkg not in pkg_data:
            pkg_data[pkg] = {"files": 0, "controllers": 0, "services": 0, "repositories": 0}
        pkg_data[pkg]["files"] += 1
        if CONTROLLER_RE.search(content):
            pkg_data[pkg]["controllers"] += 1
        if SERVICE_RE.search(content):
            pkg_data[pkg]["services"] += 1
        if REPOSITORY_RE.search(content):
            pkg_data[pkg]["repositories"] += 1
    return pkg_data


def cluster_modules(pkg_data: dict, keywords: list) -> list:
    """Cluster packages into module candidates by common prefix."""
    # Collect all prefixes at depth 3-5
    prefix_stats = {}
    for pkg, stats in pkg_data.items():
        parts = pkg.split(".")
        for depth in range(min(3, len(parts)), min(len(parts) + 1, 6)):
            prefix = ".".join(parts[:depth])
            if prefix not in prefix_stats:
                prefix_stats[prefix] = {
                    "files": 0, "controllers": 0, "services": 0,
                    "repositories": 0, "sub_packages": set(),
                }
            prefix_stats[prefix]["files"] += stats["files"]
            prefix_stats[prefix]["controllers"] += stats["controllers"]
            prefix_stats[prefix]["services"] += stats["services"]
            prefix_stats[prefix]["repositories"] += stats["repositories"]
            prefix_stats[prefix]["sub_packages"].add(pkg)

    # Score each prefix
    candidates = []
    for prefix, stats in prefix_stats.items():
        # Must have at least one controller or service
        if stats["controllers"] == 0 and stats["services"] == 0:
            continue
        depth = len(prefix.split("."))
        if depth < 3:
            continue  # Too broad

        score = (
            stats["controllers"] * 2.0 +
            stats["services"] * 1.5 +
            stats["repositories"] * 1.5 +
            stats["files"] * 0.1
        )
        # Keyword boost
        last_segment = prefix.split(".")[-1].lower()
        for kw in keywords:
            if kw.lower() in last_segment:
                score *= 1.5
                break

        candidates.append({
            "module_key": last_segment,
            "package_prefix": prefix,
            "file_count": stats["files"],
            "controller_count": stats["controllers"],
            "service_count": stats["services"],
            "repository_count": stats["repositories"],
            "sub_package_count": len(stats["sub_packages"]),
            "score": round(score, 2),
        })

    # Sort by score descending
    candidates.sort(key=lambda c: c["score"], reverse=True)

    # Deduplicate: if a child prefix is fully contained in a parent with same files, keep higher-scored
    filtered = []
    seen_keys = set()
    for c in candidates:
        # Skip if this module_key's broader prefix already captured
        is_child = False
        for existing in filtered:
            if c["package_prefix"].startswith(existing["package_prefix"] + ".") and \
               c["file_count"] <= existing["file_count"]:
                is_child = True
                break
        if is_child:
            continue
        # Skip duplicate module_key with lower score
        if c["module_key"] in seen_keys:
            continue
        seen_keys.add(c["module_key"])
        filtered.append(c)

    return filtered


def compute_confidence(candidates: list, idx: int) -> float:
    """Compute confidence for candidate at index."""
    if not candidates:
        return 0.0
    top_score = candidates[0]["score"]
    if top_score == 0:
        return 0.0
    c = candidates[idx]
    base = min(0.95, 0.5 + c["score"] / (top_score * 2))
    if idx == 0 and len(candidates) > 1:
        ratio = candidates[1]["score"] / top_score
        if ratio > 0.8:
            base *= 0.8  # Ambiguous
    return round(base, 2)


def main():
    parser = argparse.ArgumentParser(
        description="Auto-discover module candidates in a repo (no --module-key required)")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--keywords", default="", help="Comma-separated keywords to boost")
    parser.add_argument("--top-k", type=int, default=10, help="Max candidates to return")
    parser.add_argument("--out", default=None, help="Output file (default: stdout)")
    parser.add_argument("--read-only", action="store_true", help="No fs writes; stdout only")
    args = parser.parse_args()

    t_start = time.time()
    repo_root = Path(args.repo_root).resolve()
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    java_roots = find_java_roots(repo_root)
    if not java_roots:
        print("[auto_module_discover] WARN: no src/main/java found")

    all_pkgs = {}
    for jr in java_roots:
        for pkg, stats in scan_packages(jr).items():
            if pkg not in all_pkgs:
                all_pkgs[pkg] = {"files": 0, "controllers": 0, "services": 0, "repositories": 0}
            for k in ("files", "controllers", "services", "repositories"):
                all_pkgs[pkg][k] += stats[k]

    candidates = cluster_modules(all_pkgs, keywords)[:args.top_k]

    scan_time = time.time() - t_start

    # Build output
    lines = [
        "# Auto-generated by auto_module_discover.py",
        f"# scan_time: {scan_time:.3f}s",
        f"# java_roots: {len(java_roots)}",
        f"# total_packages: {len(all_pkgs)}",
        f"# candidates: {len(candidates)}",
        "",
        "module_candidates:",
    ]
    for i, c in enumerate(candidates):
        conf = compute_confidence(candidates, i)
        lines.append(f'  - module_key: "{c["module_key"]}"')
        lines.append(f'    package_prefix: "{c["package_prefix"]}"')
        lines.append(f"    file_count: {c['file_count']}")
        lines.append(f"    controller_count: {c['controller_count']}")
        lines.append(f"    service_count: {c['service_count']}")
        lines.append(f"    repository_count: {c['repository_count']}")
        lines.append(f"    score: {c['score']}")
        lines.append(f"    confidence: {conf}")

    output = "\n".join(lines) + "\n"

    if args.out and not args.read_only:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"[auto_module_discover] output: {out_path}")
    else:
        print(output, end="")

    print(f"[auto_module_discover] candidates: {len(candidates)}, scan_time: {scan_time:.3f}s", file=sys.stderr)
    for c in candidates[:5]:
        print(f"  [{c['module_key']}] {c['package_prefix']} (score={c['score']})", file=sys.stderr)


if __name__ == "__main__":
    main()
