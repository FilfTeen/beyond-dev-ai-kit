#!/usr/bin/env python3
"""Layout adapters v1 for hongzhi_ai_kit discover.

Purpose:
- Detect broader project layouts and scan roots (including non-standard Java roots).
- Derive module roots entries from candidates and optional identity hints.
- Keep output machine-readable and dependency-free.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

IGNORE_DIRS = {
    ".git", ".svn", "node_modules", "target", "dist", ".idea", "__pycache__",
    "build", "out", "_regression_tmp", ".structure_cache", ".gradle", ".mvn",
    "generated-sources", "generated-test-sources", "test-classes", "classes",
}

JAVA_SUFFIXES = (
    "src/main/java",
    "java",
    "app/src/main/java",
    "backend/src/main/java",
)

TEMPLATE_SUFFIXES = (
    "src/main/resources/templates",
    "templates",
    "src/main/webapp",
    "webapp",
)


def _dedup(seq: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in seq:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _path_to_rel(path_obj: Path, repo_root: Path) -> str:
    try:
        return str(path_obj.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except Exception:
        return str(path_obj)


def detect_roots(repo_root: Path) -> Dict[str, List[str]]:
    repo_root = Path(repo_root).resolve()
    java_roots: List[str] = []
    template_roots: List[str] = []

    for root, dirs, _files in os.walk(str(repo_root)):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        current = Path(root)
        try:
            rel = str(current.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            continue
        rel = rel.strip("/")
        if not rel:
            continue

        for suffix in JAVA_SUFFIXES:
            if rel == suffix or rel.endswith("/" + suffix):
                java_roots.append(str(current.resolve()))
                break

        for suffix in TEMPLATE_SUFFIXES:
            if rel == suffix or rel.endswith("/" + suffix):
                template_roots.append(str(current.resolve()))
                break

    return {
        "java_roots": _dedup(java_roots),
        "template_roots": _dedup(template_roots),
    }


def classify_layout(repo_root: Path, java_roots: List[str]) -> str:
    repo_root = Path(repo_root).resolve()
    root_pom = repo_root / "pom.xml"
    if root_pom.exists():
        try:
            text = root_pom.read_text(encoding="utf-8", errors="ignore")
            if "<modules>" in text:
                return "multi-module-maven"
        except OSError:
            pass
        return "single-module-maven"

    nonstandard = False
    for root in java_roots:
        rel = _path_to_rel(Path(root), repo_root)
        if rel in ("java", "app/src/main/java", "backend/src/main/java"):
            nonstandard = True
            break
        if rel.endswith("/java") and not rel.endswith("src/main/java"):
            nonstandard = True
            break

    if nonstandard:
        return "nonstandard-java-root"

    if (repo_root / "build.gradle").exists() or (repo_root / "build.gradle.kts").exists():
        return "gradle"
    if java_roots:
        return "single-module-java"
    return "unknown"


def _resolve_backend_root_candidates(repo_root: Path, java_roots: List[str], package_prefix: str) -> List[str]:
    rels: List[str] = []
    pkg_rel = package_prefix.replace(".", "/") if package_prefix else ""

    for root in java_roots:
        root_path = Path(root)
        if pkg_rel:
            target = root_path / pkg_rel
            if target.exists():
                rels.append(_path_to_rel(target, repo_root))
            else:
                rels.append(_path_to_rel(target, repo_root))
        else:
            rels.append(_path_to_rel(root_path, repo_root))

    return _dedup(rels)


def _resolve_template_root_candidates(repo_root: Path, template_roots: List[str], module_key: str) -> List[str]:
    module_key_l = (module_key or "").lower()
    rels: List[str] = []
    for root in template_roots:
        root_path = Path(root)
        if module_key_l:
            matched = False
            for cand in root_path.rglob("*"):
                if cand.is_dir() and module_key_l in cand.name.lower():
                    rels.append(_path_to_rel(cand, repo_root))
                    matched = True
                    break
            if not matched:
                rels.append(_path_to_rel(root_path, repo_root))
        else:
            rels.append(_path_to_rel(root_path, repo_root))
    return _dedup(rels)


def build_roots_entries(
    repo_root: Path,
    candidates: List[dict],
    java_roots: List[str],
    template_roots: List[str],
) -> List[dict]:
    repo_root = Path(repo_root).resolve()
    entries: List[dict] = []

    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        module_key = str(cand.get("module_key") or "").strip()
        package_prefix = str(cand.get("package_prefix") or "").strip()
        if not module_key and not package_prefix:
            continue

        backend_paths = _resolve_backend_root_candidates(repo_root, java_roots, package_prefix)
        template_paths = _resolve_template_root_candidates(repo_root, template_roots, module_key)

        roots = []
        for path in backend_paths:
            roots.append({"kind": "backend_java", "path": path})
        for path in template_paths:
            roots.append({"kind": "web_template", "path": path})

        entries.append(
            {
                "module_key": module_key,
                "package_prefix": package_prefix,
                "roots": roots,
            }
        )

    return entries


def analyze_layout(
    repo_root: Path,
    candidates: List[dict],
    keywords: List[str] | None = None,
    hint_identity: Dict[str, Any] | None = None,
    fallback_layout: str = "unknown",
) -> Dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    roots = detect_roots(repo_root)
    java_roots = roots.get("java_roots", [])
    template_roots = roots.get("template_roots", [])

    layout = classify_layout(repo_root, java_roots)
    if layout == "unknown" and fallback_layout:
        layout = fallback_layout

    entries = build_roots_entries(repo_root, candidates, java_roots, template_roots)

    fallback_reason = ""
    if not java_roots:
        fallback_reason = "no_java_roots_detected"
    elif candidates and not entries:
        fallback_reason = "candidates_unmapped"

    details = {
        "adapter_used": "layout_adapters_v1",
        "candidates_scanned": len(candidates or []),
        "java_roots_detected": len(java_roots),
        "template_roots_detected": len(template_roots),
        "keywords_used": len(keywords or []),
        "hint_identity_present": bool(hint_identity),
        "fallback_reason": fallback_reason,
    }

    return {
        "layout": layout,
        "roots_entries": entries,
        "java_roots": java_roots,
        "template_roots": template_roots,
        "layout_details": details,
    }
