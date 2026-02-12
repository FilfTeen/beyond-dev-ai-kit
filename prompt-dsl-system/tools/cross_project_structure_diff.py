#!/usr/bin/env python3
"""Cross-Project Structure Diff v2 — compare module structures across projects.

Compares old_project vs new_project for a given module_key.
Outputs: missing_classes, new_classes, missing_templates, endpoint signature changes.

V2: compares endpoint signatures (path + http_method + handler), not just paths.
Standard-library only. Python 3.9+ compatible.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Shared ignore list — canonical
IGNORE_DIRS = frozenset({
    ".git", ".svn", "node_modules", "target", "dist", ".idea",
    "__pycache__", "build", "out", "_regression_tmp", ".structure_cache",
    ".gradle", ".mvn", "generated-sources", "generated-test-sources",
    "test-classes", "classes",
})

TEMPLATE_EXTENSIONS = frozenset({".html", ".htm", ".ftl", ".jsp", ".vue", ".tpl"})

# Endpoint v2 patterns (same as structure_discover v2)
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

HTTP_METHOD_MAP = {
    "Get": "GET", "Post": "POST", "Put": "PUT",
    "Delete": "DELETE", "Patch": "PATCH", "Request": "ANY",
}


def normalize_path(base, segment):
    base = base.rstrip("/") if base else ""
    segment = segment.lstrip("/") if segment else ""
    if not base and not segment:
        return "/"
    if not segment:
        return "/" + base.lstrip("/")
    return "/" + (base.lstrip("/") + "/" + segment).replace("//", "/")


def extract_endpoint_sigs(content, class_name):
    """Extract v2 endpoint signatures from a Java source file."""
    sigs = []
    class_base = ""
    class_produces = ""
    class_consumes = ""
    cm = CLASS_MAPPING_RE.search(content)
    if cm:
        class_base = cm.group(1) or ""
        class_produces = cm.group(2) or ""
        class_consumes = cm.group(3) or ""

    for mm in METHOD_MAPPING_RE.finditer(content):
        mapping_type = mm.group(1)
        path_segment = mm.group(2) or ""
        produces = mm.group(3) or class_produces
        consumes = mm.group(4) or class_consumes
        http_method = HTTP_METHOD_MAP.get(mapping_type, "ANY")
        full_path = normalize_path(class_base, path_segment)

        pos = mm.end()
        method_match = re.search(r'(?:public|private|protected)\s+\S+\s+(\w+)', content[pos:pos + 200])
        method_name = method_match.group(1) if method_match else "unknown"

        sig = {
            "path": full_path,
            "http_method": http_method,
            "class": class_name,
            "method": method_name,
        }
        if produces:
            sig["produces"] = produces
        if consumes:
            sig["consumes"] = consumes
        sigs.append(sig)
    return sigs


def scan_classes(root, module_key):
    """Scan Java classes related to a module with v2 endpoint signatures."""
    classes = {}
    for p in root.rglob("*.java"):
        if any(ex in p.parts for ex in IGNORE_DIRS):
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        pkg_match = re.search(r'^package\s+([\w.]+)\s*;', content, re.MULTILINE)
        pkg = pkg_match.group(1) if pkg_match else ""
        if module_key.lower() not in pkg.lower() and module_key.lower() not in p.name.lower():
            continue

        cls_match = re.search(r'(?:class|interface)\s+(\w+)', content)
        cls_name = cls_match.group(1) if cls_match else p.stem

        sigs = extract_endpoint_sigs(content, cls_name)
        classes[cls_name] = {
            "file": str(p.relative_to(root)).replace("\\", "/"),
            "package": pkg,
            "endpoint_signatures": sigs,
        }
    return classes


def scan_templates(root, module_key):
    """Scan templates related to a module."""
    templates = set()
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(ex in p.parts for ex in IGNORE_DIRS):
            continue
        if p.suffix.lower() not in TEMPLATE_EXTENSIONS:
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        if module_key.lower() in rel.lower():
            templates.add(p.name)
    return templates


def load_scan_graph(path: str) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def scan_classes_from_graph(graph: dict, module_key: str):
    classes = {}
    hints = graph.get("java_hints", []) if isinstance(graph.get("java_hints"), list) else []
    module_key_l = str(module_key or "").lower()
    for hint in hints:
        if not isinstance(hint, dict):
            continue
        rel = str(hint.get("rel_path", "") or "")
        pkg = str(hint.get("package", "") or "")
        cls_name = str(hint.get("class_name", "") or "") or Path(rel).stem
        if module_key_l and module_key_l not in pkg.lower() and module_key_l not in rel.lower() and module_key_l not in cls_name.lower():
            continue
        key = cls_name if cls_name not in classes else f"{cls_name}@{rel}"
        classes[key] = {
            "file": rel,
            "package": pkg,
            "endpoint_signatures": hint.get("endpoint_signatures", []) if isinstance(hint.get("endpoint_signatures", []), list) else [],
        }
    return classes


def scan_templates_from_graph(graph: dict, module_key: str):
    templates = set()
    file_index = graph.get("file_index", {}) if isinstance(graph.get("file_index"), dict) else {}
    entries = file_index.get("templates", []) if isinstance(file_index.get("templates"), list) else []
    module_key_l = str(module_key or "").lower()
    for item in entries:
        rel = ""
        if isinstance(item, dict):
            rel = str(item.get("relpath", "") or "")
        elif isinstance(item, str):
            rel = item
        if not rel:
            continue
        if module_key_l and module_key_l not in rel.lower():
            continue
        templates.add(Path(rel).name)
    return templates


def sig_key(sig):
    """Create a comparable key for an endpoint signature."""
    return (sig["path"], sig["http_method"])


def diff_structures(old_classes, new_classes, old_templates, new_templates):
    """Compute structural diff between old and new project (v2: endpoint signatures)."""
    old_names = set(old_classes.keys())
    new_names = set(new_classes.keys())

    missing_classes = sorted(old_names - new_names)
    new_class_list = sorted(new_names - old_names)

    # V2 endpoint signature diff
    endpoint_diff = {
        "added": [],
        "removed": [],
        "changed": [],
    }
    for cls in sorted(old_names & new_names):
        old_sigs = old_classes[cls]["endpoint_signatures"]
        new_sigs = new_classes[cls]["endpoint_signatures"]

        old_map = {sig_key(s): s for s in old_sigs}
        new_map = {sig_key(s): s for s in new_sigs}

        old_keys = set(old_map.keys())
        new_keys = set(new_map.keys())

        for k in sorted(old_keys - new_keys):
            endpoint_diff["removed"].append(old_map[k])
        for k in sorted(new_keys - old_keys):
            endpoint_diff["added"].append(new_map[k])
        for k in sorted(old_keys & new_keys):
            os_sig = old_map[k]
            ns_sig = new_map[k]
            # Changed = same path+method but different handler, consumes, or produces
            if (os_sig.get("method") != ns_sig.get("method") or
                os_sig.get("produces") != ns_sig.get("produces") or
                    os_sig.get("consumes") != ns_sig.get("consumes")):
                endpoint_diff["changed"].append({
                    "old": os_sig,
                    "new": ns_sig,
                })

    missing_templates = sorted(old_templates - new_templates)
    new_template_list = sorted(new_templates - old_templates)

    return {
        "missing_classes": missing_classes,
        "new_classes": new_class_list,
        "missing_templates": missing_templates,
        "new_templates": new_template_list,
        "endpoint_diff": endpoint_diff,
    }


def format_sig(sig):
    """Format a signature for YAML output."""
    parts = [f'path: "{sig["path"]}"', f'http_method: "{sig["http_method"]}"',
             f'class: "{sig["class"]}"', f'method: "{sig["method"]}"']
    if sig.get("produces"):
        parts.append(f'produces: "{sig["produces"]}"')
    if sig.get("consumes"):
        parts.append(f'consumes: "{sig["consumes"]}"')
    return parts


def write_diff_report(out_path, module_key, diff, old_root, new_root, scan_time,
                       read_only=False):
    """Write diff report as YAML."""
    lines = [
        "# Auto-generated by cross_project_structure_diff.py v2",
        "",
        "diff_metadata:",
        f'  module_key: "{module_key}"',
        f'  old_project: "{old_root}"',
        f'  new_project: "{new_root}"',
        f'  generated_at: "{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}"',
        f"  scan_time_seconds: {scan_time:.3f}",
        "",
        "structure_diff:",
        "  missing_classes:",
    ]
    for c in diff["missing_classes"]:
        lines.append(f'    - "{c}"')
    lines.append("  new_classes:")
    for c in diff["new_classes"]:
        lines.append(f'    - "{c}"')
    lines.append("  missing_templates:")
    for t in diff["missing_templates"]:
        lines.append(f'    - "{t}"')
    lines.append("  new_templates:")
    for t in diff["new_templates"]:
        lines.append(f'    - "{t}"')

    # V2 endpoint signature diff
    ep_diff = diff["endpoint_diff"]
    lines.append("  endpoint_signatures:")
    lines.append("    removed:")
    for sig in ep_diff["removed"]:
        parts = format_sig(sig)
        lines.append("      - {" + ", ".join(parts) + "}")
    lines.append("    added:")
    for sig in ep_diff["added"]:
        parts = format_sig(sig)
        lines.append("      - {" + ", ".join(parts) + "}")
    lines.append("    changed:")
    for ch in ep_diff["changed"]:
        lines.append("      - old: {" + ", ".join(format_sig(ch["old"])) + "}")
        lines.append("        new: {" + ", ".join(format_sig(ch["new"])) + "}")

    # Summary
    lines.append("")
    lines.append("summary:")
    lines.append(f"  missing_class_count: {len(diff['missing_classes'])}")
    lines.append(f"  new_class_count: {len(diff['new_classes'])}")
    lines.append(f"  missing_template_count: {len(diff['missing_templates'])}")
    lines.append(f"  new_template_count: {len(diff['new_templates'])}")
    lines.append(f"  endpoint_removed_count: {len(ep_diff['removed'])}")
    lines.append(f"  endpoint_added_count: {len(ep_diff['added'])}")
    lines.append(f"  endpoint_changed_count: {len(ep_diff['changed'])}")

    output = "\n".join(lines) + "\n"

    if read_only:
        print(output, end="")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Compare module structure between old and new project (v2: endpoint signatures)")
    parser.add_argument("--old-project-root", required=True, help="Old project root")
    parser.add_argument("--new-project-root", required=True, help="New project root")
    parser.add_argument("--module-key", required=True, help="Module identifier")
    parser.add_argument("--old-scan-graph", default=None, help="Optional old-side scan_graph.json path")
    parser.add_argument("--new-scan-graph", default=None, help="Optional new-side scan_graph.json path")
    parser.add_argument("--out", default=None, help="Output path")
    parser.add_argument("--read-only", action="store_true", help="No fs writes; stdout only")
    args = parser.parse_args()

    t_start = time.time()
    old_root = Path(args.old_project_root).resolve()
    new_root = Path(args.new_project_root).resolve()

    if not old_root.is_dir():
        print(f"FAIL: old project root not found: {old_root}", file=sys.stderr)
        sys.exit(1)
    if not new_root.is_dir():
        print(f"FAIL: new project root not found: {new_root}", file=sys.stderr)
        sys.exit(1)

    old_graph = load_scan_graph(args.old_scan_graph) if args.old_scan_graph else {}
    new_graph = load_scan_graph(args.new_scan_graph) if args.new_scan_graph else {}
    if old_graph and new_graph:
        old_classes = scan_classes_from_graph(old_graph, args.module_key)
        new_classes = scan_classes_from_graph(new_graph, args.module_key)
        old_templates = scan_templates_from_graph(old_graph, args.module_key)
        new_templates = scan_templates_from_graph(new_graph, args.module_key)
        print(
            f"[cross_project_diff] using scan graphs old={args.old_scan_graph} new={args.new_scan_graph}",
            file=sys.stderr,
        )
    else:
        old_classes = scan_classes(old_root, args.module_key)
        new_classes = scan_classes(new_root, args.module_key)
        old_templates = scan_templates(old_root, args.module_key)
        new_templates = scan_templates(new_root, args.module_key)

    diff = diff_structures(old_classes, new_classes, old_templates, new_templates)

    scan_time = time.time() - t_start

    if args.out:
        out_path = Path(args.out)
    else:
        out_path = Path(f"structure_diff_{args.module_key}.yaml")

    write_diff_report(out_path, args.module_key, diff,
                       str(old_root), str(new_root), scan_time,
                       read_only=args.read_only)

    print(f"[cross_project_diff] old classes: {len(old_classes)}, new classes: {len(new_classes)}", file=sys.stderr)
    print(f"[cross_project_diff] missing: {len(diff['missing_classes'])}, new: {len(diff['new_classes'])}", file=sys.stderr)
    print(f"[cross_project_diff] template diff: -{len(diff['missing_templates'])} +{len(diff['new_templates'])}", file=sys.stderr)
    ep = diff["endpoint_diff"]
    print(f"[cross_project_diff] endpoint sigs: -{len(ep['removed'])} +{len(ep['added'])} ~{len(ep['changed'])}", file=sys.stderr)
    print(f"[cross_project_diff] scan time: {scan_time:.3f}s", file=sys.stderr)
    if not args.read_only:
        print(f"[cross_project_diff] output: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
