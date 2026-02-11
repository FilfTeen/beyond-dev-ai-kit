#!/usr/bin/env python3
"""Structure Discover v2 — auto-identify module structure without identity hints.

Scans Java packages, controllers, services, mappers, templates, and API endpoints.
Uses package prefix clustering to infer module identity.
Outputs structure_discovered.yaml (Layer2S).

V2 features:
  - Endpoint extraction v2: class-level + method-level @RequestMapping join,
    HTTP method inference, consumes/produces, normalized paths
  - Per-file incremental cache: .structure_cache/<root_hash>.index.json
  - Output control: --out-root, --read-only
  - Shared robust ignore list

Performance: concurrent scanning, per-file caching, incremental mtime skip.
Standard-library only. Python 3.9+ compatible.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

SCANNER_VERSION = "2.0"
CACHE_DIR_NAME = ".structure_cache"

# Shared ignore list — canonical for all discovery tools
IGNORE_DIRS = frozenset({
    ".git", ".svn", "node_modules", "target", "dist", ".idea",
    "__pycache__", "build", "out", "_regression_tmp", CACHE_DIR_NAME,
    ".gradle", ".mvn", "generated-sources", "generated-test-sources",
    "test-classes", "classes",
})

# Java structural patterns
CONTROLLER_PATTERN = re.compile(r'@(Rest)?Controller|@RequestMapping|@GetMapping|@PostMapping|@PutMapping|@DeleteMapping')
SERVICE_PATTERN = re.compile(r'@Service|class\s+\w+Service\w*')
REPOSITORY_PATTERN = re.compile(r'@Repository|@Mapper|interface\s+\w+Mapper|interface\s+\w+Repository')
ENTITY_PATTERN = re.compile(r'@Entity|@Table|class\s+\w+Entity')
DTO_PATTERN = re.compile(r'class\s+\w+(Dto|DTO|Vo|VO)\b')

# Endpoint v2 patterns
CLASS_MAPPING_RE = re.compile(
    r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']'
    r'(?:.*?produces\s*=\s*["\']([^"\']+)["\'])?'
    r'(?:.*?consumes\s*=\s*["\']([^"\']+)["\'])?'
    r'\s*\)', re.DOTALL)

METHOD_MAPPING_RE = re.compile(
    r'@(Get|Post|Put|Delete|Patch|Request)Mapping\s*\(\s*'
    r'(?:value\s*=\s*)?["\']([^"\']+)["\']'
    r'(?:.*?produces\s*=\s*["\']([^"\']+)["\'])?'
    r'(?:.*?consumes\s*=\s*["\']([^"\']+)["\'])?'
    r'\s*\)', re.DOTALL)

# Simple method-level mapping without value (just annotation)
SIMPLE_METHOD_MAPPING_RE = re.compile(
    r'@(Get|Post|Put|Delete|Patch)Mapping\s*(?:\(\s*\))?\s*\n\s*(?:public|private|protected)\s+\S+\s+(\w+)')

# Template structural patterns
TEMPLATE_EXTENSIONS = frozenset({".html", ".htm", ".ftl", ".jsp", ".vue", ".tpl"})

HTTP_METHOD_MAP = {
    "Get": "GET", "Post": "POST", "Put": "PUT",
    "Delete": "DELETE", "Patch": "PATCH", "Request": "ANY",
}


def root_hash(root_path: str) -> str:
    """Compute stable hash for a root path."""
    return hashlib.md5(root_path.encode()).hexdigest()[:12]


def load_file_index(cache_dir: Path, rh: str) -> dict:
    """Load per-file index from cache."""
    idx_file = cache_dir / f"{rh}.index.json"
    if idx_file.exists():
        try:
            return json.loads(idx_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_file_index(cache_dir: Path, rh: str, index: dict):
    """Save per-file index to cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    idx_file = cache_dir / f"{rh}.index.json"
    try:
        idx_file.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def normalize_path(base: str, segment: str) -> str:
    """Join and normalize endpoint paths."""
    base = base.rstrip("/") if base else ""
    segment = segment.lstrip("/") if segment else ""
    if not base and not segment:
        return "/"
    if not segment:
        return "/" + base.lstrip("/")
    return "/" + (base.lstrip("/") + "/" + segment).replace("//", "/")


def extract_endpoints_v2(content: str, class_name: str) -> list:
    """Extract API endpoint signatures with class+method join, HTTP method, consumes/produces."""
    endpoints = []

    # Find class-level @RequestMapping
    class_base = ""
    class_produces = ""
    class_consumes = ""
    cm = CLASS_MAPPING_RE.search(content)
    if cm:
        class_base = cm.group(1) or ""
        class_produces = cm.group(2) or ""
        class_consumes = cm.group(3) or ""

    # Find method-level mappings with value
    for mm in METHOD_MAPPING_RE.finditer(content):
        mapping_type = mm.group(1)
        path_segment = mm.group(2) or ""
        produces = mm.group(3) or class_produces
        consumes = mm.group(4) or class_consumes
        http_method = HTTP_METHOD_MAP.get(mapping_type, "ANY")

        full_path = normalize_path(class_base, path_segment)

        # Try to find method name after this annotation
        pos = mm.end()
        method_match = re.search(r'(?:public|private|protected)\s+\S+\s+(\w+)', content[pos:pos+200])
        method_name = method_match.group(1) if method_match else "unknown"

        ep = {
            "path": full_path,
            "http_method": http_method,
            "class": class_name,
            "method": method_name,
        }
        if produces:
            ep["produces"] = produces
        if consumes:
            ep["consumes"] = consumes
        endpoints.append(ep)

    # Find simple method mappings (no value)
    for sm in SIMPLE_METHOD_MAPPING_RE.finditer(content):
        mapping_type = sm.group(1)
        method_name = sm.group(2)
        http_method = HTTP_METHOD_MAP.get(mapping_type, "ANY")
        full_path = normalize_path(class_base, "")

        # Avoid duplicating already-found endpoints
        if not any(e["method"] == method_name for e in endpoints):
            ep = {
                "path": full_path,
                "http_method": http_method,
                "class": class_name,
                "method": method_name,
            }
            if class_produces:
                ep["produces"] = class_produces
            if class_consumes:
                ep["consumes"] = class_consumes
            endpoints.append(ep)

    return endpoints


def scan_java_file(file_path: Path, repo_root: Path) -> dict:
    """Scan a single Java file for structural elements + v2 endpoints."""
    rel = str(file_path.relative_to(repo_root)).replace("\\", "/")
    result = {
        "rel_path": rel,
        "package": "",
        "is_controller": False,
        "is_service": False,
        "is_repository": False,
        "is_entity": False,
        "is_dto": False,
        "endpoints": [],
        "endpoint_signatures": [],
        "class_name": "",
    }
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return result

    # Extract package
    pkg_match = re.search(r'^package\s+([\w.]+)\s*;', content, re.MULTILINE)
    if pkg_match:
        result["package"] = pkg_match.group(1)

    # Extract class name
    cls_match = re.search(r'(?:class|interface)\s+(\w+)', content)
    if cls_match:
        result["class_name"] = cls_match.group(1)

    # Detect structural role
    if CONTROLLER_PATTERN.search(content):
        result["is_controller"] = True
    if SERVICE_PATTERN.search(content):
        result["is_service"] = True
    if REPOSITORY_PATTERN.search(content):
        result["is_repository"] = True
    if ENTITY_PATTERN.search(content):
        result["is_entity"] = True
    if DTO_PATTERN.search(content):
        result["is_dto"] = True

    # V2 endpoint extraction
    if result["is_controller"] and result["class_name"]:
        sigs = extract_endpoints_v2(content, result["class_name"])
        result["endpoint_signatures"] = sigs
        result["endpoints"] = [s["path"] for s in sigs]

    return result


def scan_java_root_incremental(root: Path, repo_root: Path, file_index: dict) -> tuple:
    """Scan Java files with per-file incremental caching.
    Returns: (results_list, updated_file_index, cache_hits, cache_misses)
    """
    java_files = []
    for p in root.rglob("*.java"):
        if any(ex in p.parts for ex in IGNORE_DIRS):
            continue
        java_files.append(p)

    results = []
    cache_hits = 0
    cache_misses = 0
    new_index = {}

    def process_file(fp):
        nonlocal cache_hits, cache_misses
        rel = str(fp.relative_to(repo_root)).replace("\\", "/")
        try:
            st = fp.stat()
            mtime = st.st_mtime
            size = st.st_size
        except OSError:
            return None

        # Check per-file cache
        cached = file_index.get(rel)
        if cached and cached.get("mtime") == mtime and cached.get("size") == size:
            cache_hits += 1
            new_index[rel] = cached
            return cached.get("features")
        else:
            cache_misses += 1
            result = scan_java_file(fp, repo_root)
            # Store in new index (strip non-serializable)
            new_index[rel] = {
                "mtime": mtime,
                "size": size,
                "features": result,
            }
            return result

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(java_files) // 10 + 1))) as executor:
        futures = {executor.submit(process_file, f): f for f in java_files}
        for future in as_completed(futures):
            try:
                r = future.result()
                if r:
                    results.append(r)
            except Exception:
                pass

    return results, new_index, cache_hits, cache_misses


def scan_templates(root, repo_root):
    """Scan template files under a root."""
    templates = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(ex in p.parts for ex in IGNORE_DIRS):
            continue
        if p.suffix.lower() in TEMPLATE_EXTENSIONS:
            templates.append(str(p.relative_to(repo_root)).replace("\\", "/"))
    return templates


def cluster_packages(java_results):
    """Cluster Java files by package prefix to infer modules."""
    pkg_files = {}
    for r in java_results:
        pkg = r["package"]
        if not pkg:
            continue
        pkg_files.setdefault(pkg, []).append(r)

    if not pkg_files:
        return []

    prefix_counter = {}
    for pkg, files in pkg_files.items():
        parts = pkg.split(".")
        for depth in range(min(3, len(parts)), min(len(parts) + 1, 7)):
            prefix = ".".join(parts[:depth])
            if prefix not in prefix_counter:
                prefix_counter[prefix] = {
                    "files": [],
                    "controller_count": 0, "service_count": 0,
                    "repository_count": 0, "entity_count": 0,
                    "dto_count": 0, "endpoint_count": 0,
                    "packages": set(),
                }
            for f in files:
                if f not in prefix_counter[prefix]["files"]:
                    prefix_counter[prefix]["files"].append(f)
                    prefix_counter[prefix]["packages"].add(pkg)
                    if f["is_controller"]:
                        prefix_counter[prefix]["controller_count"] += 1
                    if f["is_service"]:
                        prefix_counter[prefix]["service_count"] += 1
                    if f["is_repository"]:
                        prefix_counter[prefix]["repository_count"] += 1
                    if f["is_entity"]:
                        prefix_counter[prefix]["entity_count"] += 1
                    if f["is_dto"]:
                        prefix_counter[prefix]["dto_count"] += 1
                    prefix_counter[prefix]["endpoint_count"] += len(f.get("endpoints", []))

    clusters = []
    for prefix, data in prefix_counter.items():
        if data["controller_count"] == 0 and data["service_count"] == 0:
            continue
        score = (
            data["controller_count"] * 2.0 +
            data["service_count"] * 1.5 +
            data["repository_count"] * 1.5 +
            data["entity_count"] * 0.5 +
            data["dto_count"] * 0.5 +
            data["endpoint_count"] * 2.0
        )
        depth = len(prefix.split("."))
        if depth < 3:
            score *= 0.5
        clusters.append({
            "prefix": prefix,
            "file_count": len(data["files"]),
            "score": round(score, 2),
            "controller_count": data["controller_count"],
            "service_count": data["service_count"],
            "repository_count": data["repository_count"],
            "entity_count": data["entity_count"],
            "dto_count": data["dto_count"],
            "endpoint_count": data["endpoint_count"],
            "packages": sorted(data["packages"]),
        })

    clusters.sort(key=lambda c: c["score"], reverse=True)

    filtered = []
    for c in clusters:
        is_subset = False
        for existing in filtered:
            if c["prefix"].startswith(existing["prefix"] + ".") and c["file_count"] <= existing["file_count"]:
                is_subset = True
                break
            if existing["prefix"].startswith(c["prefix"] + "."):
                is_subset = True
                break
        if not is_subset:
            filtered.append(c)

    return filtered[:20]


def compute_confidence(clusters):
    """Compute confidence score for top cluster."""
    if not clusters:
        return 0.0
    top = clusters[0]
    if len(clusters) == 1:
        return min(0.95, 0.5 + top["score"] / 100.0)
    ratio = clusters[1]["score"] / top["score"] if top["score"] > 0 else 1.0
    if ratio > 0.8:
        return max(0.3, 0.7 - ratio * 0.3)
    return min(0.95, 0.6 + (1.0 - ratio) * 0.3)


def collect_endpoint_signatures(java_results, module_key=None, prefix_filter=None):
    """Collect all v2 endpoint signatures, optionally filtered."""
    all_sigs = []
    for r in java_results:
        if not r.get("endpoint_signatures"):
            continue
        if prefix_filter and not r["package"].startswith(prefix_filter):
            continue
        if module_key and module_key.lower() not in r["package"].lower() and \
           module_key.lower() not in r["class_name"].lower():
            continue
        all_sigs.extend(r["endpoint_signatures"])
    return all_sigs


def compute_fingerprint(repo_root, paths):
    """Compute fingerprint across all scanned files."""
    file_count = 0
    total_bytes = 0
    latest_mtime = 0.0
    for rel in paths:
        p = repo_root / rel
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


def write_structure_discovered(out_path, project_key, module_key,
                                clusters, endpoint_sigs, templates,
                                fingerprint, scan_time, cache_hits, cache_misses,
                                read_only=False):
    """Write structure_discovered.yaml (Layer2S)."""
    confidence = compute_confidence(clusters)
    inferred_name = module_key
    if clusters:
        parts = clusters[0]["prefix"].split(".")
        inferred_name = parts[-1] if parts else module_key

    top = clusters[0] if clusters else {}
    lines = [
        "# Auto-generated by structure_discover.py v2 — DO NOT EDIT MANUALLY",
        "# Re-run discover to regenerate. Safe to delete.",
        "",
        'profile_kind: "structure_discovered"',
        f'profile_version: "{SCANNER_VERSION}"',
        "",
        "module_identity:",
        f'  project_key: "{project_key}"',
        f'  module_key: "{module_key}"',
        f'  inferred_module_name: "{inferred_name}"',
        f"  confidence: {confidence:.2f}",
        "",
        f'generated_at: "{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}"',
        f"scan_time_seconds: {scan_time:.3f}",
        f"cache_stats:",
        f"  cache_hit_files: {cache_hits}",
        f"  cache_miss_files: {cache_misses}",
        f"  total_files: {cache_hits + cache_misses}",
        "",
        "structure_summary:",
        f"  controller_count: {top.get('controller_count', 0)}",
        f"  service_count: {top.get('service_count', 0)}",
        f"  repository_count: {top.get('repository_count', 0)}",
        f"  entity_count: {top.get('entity_count', 0)}",
        f"  dto_count: {top.get('dto_count', 0)}",
        f"  template_count: {len(templates)}",
        f"  endpoint_count: {len(endpoint_sigs)}",
        "",
        "package_clusters:",
    ]
    for c in clusters[:10]:
        lines.append(f'  - prefix: "{c["prefix"]}"')
        lines.append(f"    files: {c['file_count']}")
        lines.append(f"    score: {c['score']}")

    lines.append("")
    lines.append("api_endpoints:")
    for ep in endpoint_sigs[:40]:
        lines.append(f'  - path: "{ep["path"]}"')
        lines.append(f'    http_method: "{ep["http_method"]}"')
        lines.append(f'    class: "{ep["class"]}"')
        lines.append(f'    method: "{ep["method"]}"')
        if ep.get("produces"):
            lines.append(f'    produces: "{ep["produces"]}"')
        if ep.get("consumes"):
            lines.append(f'    consumes: "{ep["consumes"]}"')

    lines.append("")
    lines.append("templates:")
    for t in templates[:50]:
        lines.append(f'  - "{t}"')

    lines.append("")
    lines.append("fingerprint:")
    lines.append(f'  file_count: {fingerprint["file_count"]}')
    lines.append(f'  total_bytes: {fingerprint["total_bytes"]}')
    lines.append(f'  latest_mtime: "{fingerprint["latest_mtime"]}"')

    output = "\n".join(lines) + "\n"

    if read_only:
        print(output, end="")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")


def find_scan_roots(repo_root):
    """Find Java and template scan roots automatically."""
    java_roots = []
    template_roots = []
    for root, dirs, files in os.walk(str(repo_root)):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        root_p = Path(root)
        rel = str(root_p.relative_to(repo_root)).replace("\\", "/")
        if rel.endswith("src/main/java") or rel == "src/main/java":
            java_roots.append(root_p)
        if rel.endswith("src/main/resources/templates") or rel == "src/main/resources/templates":
            template_roots.append(root_p)
    return java_roots, template_roots


def main():
    parser = argparse.ArgumentParser(
        description="Auto-discover module structure without identity hints (Layer2S v2)")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--project-key", required=True, help="Project identifier")
    parser.add_argument("--module-key", required=True, help="Module identifier")
    parser.add_argument("--out", default=None,
                        help="Output path (default: <out-root>/module_profiles/<project>/<module>.structure.discovered.yaml)")
    parser.add_argument("--out-root", "--workspace-root", default=None,
                        help="Output root directory (default: repo-root)")
    parser.add_argument("--read-only", action="store_true",
                        help="No filesystem writes; output to stdout only")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching")
    args = parser.parse_args()

    t_start = time.time()
    repo_root = Path(args.repo_root).resolve()
    out_root = Path(args.out_root).resolve() if args.out_root else repo_root

    # Setup cache
    cache_dir = out_root / "prompt-dsl-system" / "tools" / CACHE_DIR_NAME
    if args.no_cache or args.read_only:
        cache_dir = None

    # Find scan roots
    java_roots, template_roots = find_scan_roots(repo_root)
    if not java_roots and not template_roots:
        print("[structure_discover] WARN: no Java or template roots found")

    # Scan Java files with per-file incremental cache
    all_java_results = []
    total_cache_hits = 0
    total_cache_misses = 0
    for jr in java_roots:
        rh = root_hash(str(jr))
        file_idx = load_file_index(cache_dir, rh) if cache_dir else {}
        results, new_idx, hits, misses = scan_java_root_incremental(jr, repo_root, file_idx)
        all_java_results.extend(results)
        total_cache_hits += hits
        total_cache_misses += misses
        if cache_dir and not args.read_only:
            save_file_index(cache_dir, rh, new_idx)

    # Scan templates
    all_templates = []
    for tr in template_roots:
        all_templates.extend(scan_templates(tr, repo_root))

    # Cluster packages
    clusters = cluster_packages(all_java_results)

    # Filter by module_key
    module_clusters = [c for c in clusters if args.module_key.lower() in c["prefix"].lower()]
    if module_clusters:
        clusters = module_clusters + [c for c in clusters if c not in module_clusters]

    # V2 endpoints
    prefix_filter = module_clusters[0]["prefix"] if module_clusters else None
    endpoint_sigs = collect_endpoint_signatures(
        all_java_results, module_key=args.module_key, prefix_filter=prefix_filter)

    # Templates filtered
    module_templates = [t for t in all_templates if args.module_key.lower() in t.lower()]

    # Fingerprint
    all_paths = [r["rel_path"] for r in all_java_results] + all_templates
    fp = compute_fingerprint(repo_root, all_paths)

    scan_time = time.time() - t_start

    # Output
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = out_root / f"prompt-dsl-system/module_profiles/{args.project_key}/{args.module_key}.structure.discovered.yaml"

    write_structure_discovered(out_path, args.project_key, args.module_key,
                               clusters, endpoint_sigs, module_templates,
                               fp, scan_time, total_cache_hits, total_cache_misses,
                               read_only=args.read_only)

    print(f"[structure_discover] clusters found: {len(clusters)}", file=sys.stderr)
    if clusters:
        print(f"[structure_discover] top cluster: {clusters[0]['prefix']} (score={clusters[0]['score']}, files={clusters[0]['file_count']})", file=sys.stderr)
    print(f"[structure_discover] endpoint_signatures: {len(endpoint_sigs)}, templates: {len(module_templates)}", file=sys.stderr)
    print(f"[structure_discover] confidence: {compute_confidence(clusters):.2f}", file=sys.stderr)
    print(f"[structure_discover] cache: {total_cache_hits}/{total_cache_hits + total_cache_misses} hit, scan_time: {scan_time:.3f}s", file=sys.stderr)
    if not args.read_only:
        print(f"[structure_discover] output: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
