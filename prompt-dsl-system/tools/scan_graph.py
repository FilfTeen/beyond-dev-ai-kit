#!/usr/bin/env python3
from __future__ import annotations

"""
Unified Scan Graph v1

Build a single scan graph for Java/template-heavy repositories so downstream
commands (discover/profile/diff) can reuse the same indexed view and avoid
repeated full-content scans.

Standard-library only.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


SCAN_GRAPH_VERSION = "1.0.0"
SCAN_GRAPH_SCHEMA_VERSION = "1.1"

try:
    from hongzhi_ai_kit import __version__ as PACKAGE_VERSION
except Exception:
    PACKAGE_VERSION = "unknown"

IGNORE_DIRS = frozenset(
    {
        ".git",
        ".svn",
        "node_modules",
        "target",
        "dist",
        ".idea",
        "__pycache__",
        "build",
        "out",
        "_regression_tmp",
        ".structure_cache",
        ".gradle",
        ".mvn",
        "generated-sources",
        "generated-test-sources",
        "test-classes",
        "classes",
    }
)

JAVA_HINT_RE = {
    "controller": re.compile(r"@Controller|@RestController"),
    "service": re.compile(r"@Service|class\s+\w+Service\w*"),
    "repository": re.compile(r"@Repository|@Mapper|interface\s+\w+Mapper\w*"),
    "entity": re.compile(r"@Entity|@Table|class\s+\w+Entity"),
    "dto": re.compile(r"class\s+\w+(Dto|DTO|Vo|VO)\b"),
}

PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
CLASS_RE = re.compile(r"(?:class|interface)\s+(\w+)")

# Intentional "lightweight" endpoint extraction for scan graph indexing.
CLASS_MAPPING_RE = re.compile(
    r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']'
)
METHOD_MAPPING_RE = re.compile(
    r'@(Get|Post|Put|Delete|Patch|Request)Mapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']'
)
HTTP_METHOD_MAP = {
    "Get": "GET",
    "Post": "POST",
    "Put": "PUT",
    "Delete": "DELETE",
    "Patch": "PATCH",
    "Request": "ANY",
}

TEMPLATE_EXTENSIONS = frozenset({".html", ".htm", ".ftl", ".jsp", ".vue", ".tpl"})
RESOURCE_EXTENSIONS = frozenset({".yml", ".yaml", ".properties", ".xml", ".json", ".sql"})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_rel(path_obj: Path, root: Path) -> str:
    return str(path_obj.relative_to(root)).replace("\\", "/")


def is_subpath(path_obj: Path, parent_obj: Path) -> bool:
    try:
        path_obj.resolve().relative_to(parent_obj.resolve())
        return True
    except ValueError:
        return False


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = None, None
    try:
        import tempfile

        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = None
            f.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        Path(tmp_name).replace(path)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_name:
            tmp_path = Path(tmp_name)
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _bucket_by_ext(path_obj: Path) -> str:
    suffix = path_obj.suffix.lower()
    if suffix == ".java":
        return "java"
    if suffix in TEMPLATE_EXTENSIONS:
        return "templates"
    if suffix in RESOURCE_EXTENSIONS:
        return "resources"
    return "other"


def _resolve_roots(repo_root: Path, roots: Optional[Iterable[str]]) -> List[Path]:
    resolved: List[Path] = []
    items = list(roots or [])
    if not items:
        resolved.append(repo_root)
        return resolved
    for item in items:
        if not item:
            continue
        p = Path(item)
        if not p.is_absolute():
            p = (repo_root / p).resolve()
        else:
            p = p.resolve()
        if not p.is_dir():
            continue
        if not is_subpath(p, repo_root):
            continue
        if p not in resolved:
            resolved.append(p)
    if not resolved:
        resolved.append(repo_root)
    return resolved


def _iter_files(
    repo_root: Path,
    roots: List[Path],
    max_files: Optional[int],
    max_seconds: Optional[int],
) -> Tuple[List[dict], dict]:
    started = time.time()
    records: List[dict] = []
    files_seen = 0
    limit_reason = ""
    stop = False
    for root in roots:
        for current, dirs, files in os.walk(str(root)):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            if stop:
                break
            current_path = Path(current)
            for file_name in files:
                fp = current_path / file_name
                try:
                    if not fp.is_file():
                        continue
                    rel_obj = fp.relative_to(repo_root)
                    if any(part in IGNORE_DIRS for part in rel_obj.parts[:-1]):
                        continue
                    rel = str(rel_obj).replace("\\", "/")
                    st = fp.stat()
                    files_seen += 1
                except OSError:
                    continue

                records.append(
                    {
                        "relpath": rel,
                        "size": int(st.st_size),
                        "mtime_ns": int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))),
                        "ext": fp.suffix.lower(),
                        "bucket": _bucket_by_ext(fp),
                    }
                )

                if max_files is not None and len(records) >= int(max_files):
                    limit_reason = "max_files"
                    stop = True
                    break
                if max_seconds is not None and (time.time() - started) > float(max_seconds):
                    limit_reason = "max_seconds"
                    stop = True
                    break
            if stop:
                break
        if stop:
            break
    stats = {
        "files_seen": files_seen,
        "files_indexed": len(records),
        "limit_reason": limit_reason,
    }
    return records, stats


def _compute_cache_key(records: List[dict], roots: List[Path], max_files: Optional[int], max_seconds: Optional[int]) -> str:
    max_mtime = 0
    total_size = 0
    for rec in records:
        max_mtime = max(max_mtime, int(rec.get("mtime_ns", 0) or 0))
        total_size += int(rec.get("size", 0) or 0)
    parts = {
        "version": SCAN_GRAPH_VERSION,
        "roots": [str(p) for p in sorted(roots)],
        "file_count": len(records),
        "max_mtime_ns": max_mtime,
        "total_size": total_size,
        "max_files": int(max_files) if max_files is not None else None,
        "max_seconds": int(max_seconds) if max_seconds is not None else None,
    }
    encoded = json.dumps(parts, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _normalize_producer_versions(producer_versions: Optional[dict]) -> dict:
    base = {
        "package_version": PACKAGE_VERSION,
        "plugin_version": "unknown",
        "contract_version": "unknown",
    }
    if not isinstance(producer_versions, dict):
        return base
    # Accept both *_version and short keys for compatibility.
    mapping = {
        "package_version": "package_version",
        "plugin_version": "plugin_version",
        "contract_version": "contract_version",
        "package": "package_version",
        "plugin": "plugin_version",
        "contract": "contract_version",
    }
    for src_key, dst_key in mapping.items():
        if src_key in producer_versions and producer_versions.get(src_key) is not None:
            base[dst_key] = str(producer_versions.get(src_key))
    return base


def _roots_rel(repo_root: Path, roots: List[Path]) -> List[str]:
    rels: List[str] = []
    for root in roots:
        try:
            rel = normalize_rel(root.resolve(), repo_root.resolve())
        except Exception:
            rel = str(root)
        if rel == ".":
            rel = ""
        rels.append(rel)
    return sorted(set(rels))


def _compute_graph_fingerprint(file_index: dict, roots_rel: List[str], producer_versions: dict) -> str:
    hasher = hashlib.sha256()
    hasher.update(f"schema={SCAN_GRAPH_SCHEMA_VERSION}\n".encode("utf-8"))
    hasher.update(json.dumps({"roots_rel": roots_rel, "producer_versions": producer_versions}, sort_keys=True).encode("utf-8"))
    hasher.update(b"\n")
    if not isinstance(file_index, dict):
        return hasher.hexdigest()[:24]
    buckets = sorted(file_index.keys())
    for bucket in buckets:
        items = file_index.get(bucket, [])
        if not isinstance(items, list):
            continue
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                continue
            normalized.append(
                (
                    str(item.get("relpath", "")),
                    int(item.get("size", 0) or 0),
                    int(item.get("mtime_ns", 0) or 0),
                    str(item.get("ext", "")),
                )
            )
        for relpath, size, mtime_ns, ext in sorted(normalized):
            hasher.update(f"{bucket}|{relpath}|{size}|{mtime_ns}|{ext}\n".encode("utf-8"))
    return hasher.hexdigest()[:24]


def compute_graph_fingerprint_from_payload(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    producer = _normalize_producer_versions(payload.get("producer_versions"))
    roots_rel = payload.get("roots_rel", [])
    if not isinstance(roots_rel, list):
        roots_rel = []
    roots_rel = [str(x) for x in roots_rel]
    file_index = payload.get("file_index", {})
    if not isinstance(file_index, dict):
        file_index = {}
    return _compute_graph_fingerprint(file_index, roots_rel, producer)


def analyze_scan_graph_payload(
    payload: dict,
    *,
    expected_schema_version: Optional[str] = None,
    expected_producer_versions: Optional[dict] = None,
) -> Tuple[bool, str, str]:
    """
    Returns:
      (ok, mismatch_reason, mismatch_detail)
    mismatch_reason enum:
      schema_version_mismatch | fingerprint_mismatch | producer_version_mismatch | corrupted_cache | unknown
    """
    if not isinstance(payload, dict):
        return False, "corrupted_cache", "payload_not_dict"
    file_index = payload.get("file_index")
    if not isinstance(file_index, dict):
        return False, "corrupted_cache", "file_index_missing_or_invalid"

    actual_schema = str(payload.get("schema_version", "") or "")
    expected_schema = str(expected_schema_version or SCAN_GRAPH_SCHEMA_VERSION)
    if actual_schema and actual_schema != expected_schema:
        return False, "schema_version_mismatch", f"{actual_schema}!={expected_schema}"

    expected_versions = _normalize_producer_versions(expected_producer_versions)
    actual_versions = _normalize_producer_versions(payload.get("producer_versions"))
    if expected_producer_versions is not None and actual_versions != expected_versions:
        return False, "producer_version_mismatch", json.dumps({"actual": actual_versions, "expected": expected_versions}, sort_keys=True)

    expected_fp = compute_graph_fingerprint_from_payload(payload)
    actual_fp = str(payload.get("graph_fingerprint", "") or "")
    if actual_fp and expected_fp and actual_fp != expected_fp:
        return False, "fingerprint_mismatch", f"{actual_fp}!={expected_fp}"

    return True, "", ""


def _method_name_after(content: str, start: int) -> str:
    match = re.search(r"(?:public|private|protected)\s+(?:static\s+)?\S+\s+(\w+)\s*\(", content[start : start + 260])
    return match.group(1) if match else "unknown"


def _normalize_path(base: str, segment: str) -> str:
    base = str(base or "").strip().strip("/")
    seg = str(segment or "").strip().strip("/")
    if base and seg:
        return f"/{base}/{seg}".replace("//", "/")
    if base:
        return f"/{base}"
    if seg:
        return f"/{seg}"
    return "/"


def _extract_java_hint(content: str, relpath: str) -> dict:
    hint = {
        "rel_path": relpath,
        "package": "",
        "class_name": "",
        "is_controller": False,
        "is_service": False,
        "is_repository": False,
        "is_entity": False,
        "is_dto": False,
        "endpoints": [],
        "endpoint_signatures": [],
        "parse_uncertain": False,
    }
    pkg_match = PACKAGE_RE.search(content)
    if pkg_match:
        hint["package"] = pkg_match.group(1)
    cls_match = CLASS_RE.search(content)
    if cls_match:
        hint["class_name"] = cls_match.group(1)

    for key, pattern in JAVA_HINT_RE.items():
        hint[f"is_{key}"] = bool(pattern.search(content))

    class_base = ""
    cls_match = CLASS_MAPPING_RE.search(content)
    if cls_match:
        class_base = str(cls_match.group(1) or "")

    endpoints: List[dict] = []
    for mm in METHOD_MAPPING_RE.finditer(content):
        mapping_type = str(mm.group(1) or "")
        segment = str(mm.group(2) or "")
        method = HTTP_METHOD_MAP.get(mapping_type, "ANY")
        full_path = _normalize_path(class_base, segment)
        method_name = _method_name_after(content, mm.end())
        endpoints.append(
            {
                "path": full_path,
                "http_method": method,
                "class": hint["class_name"] or "unknown",
                "method": method_name,
            }
        )

    if hint["is_controller"] and "@RequestMapping(" in content and not cls_match:
        hint["parse_uncertain"] = True
    if hint["is_controller"] and ("@GetMapping(" in content or "@PostMapping(" in content) and not endpoints:
        hint["parse_uncertain"] = True
    if re.search(r'@\w+Mapping\s*\(\s*[A-Z_][\w.]*\s*\)', content):
        hint["parse_uncertain"] = True

    hint["endpoint_signatures"] = endpoints
    hint["endpoints"] = [ep.get("path", "") for ep in endpoints if isinstance(ep, dict) and ep.get("path")]
    return hint


def _build_from_records(
    repo_root: Path,
    records: List[dict],
    keywords: List[str],
) -> Tuple[dict, dict]:
    file_index: Dict[str, List[dict]] = {"java": [], "templates": [], "resources": [], "other": []}
    java_hints: List[dict] = []
    template_hints: List[dict] = []
    bytes_read = 0
    java_scanned = 0
    template_scanned = 0
    parse_uncertain_files = 0

    kws = [k.lower().strip() for k in keywords if str(k).strip()]
    for rec in records:
        bucket = rec.get("bucket", "other")
        if bucket not in file_index:
            bucket = "other"
        idx_item = {
            "relpath": rec.get("relpath", ""),
            "size": int(rec.get("size", 0) or 0),
            "mtime_ns": int(rec.get("mtime_ns", 0) or 0),
            "ext": rec.get("ext", ""),
        }
        file_index[bucket].append(idx_item)

        if bucket == "java":
            java_scanned += 1
            p = repo_root / str(rec.get("relpath", ""))
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                content = ""
            bytes_read += len(content.encode("utf-8", errors="ignore"))
            hint = _extract_java_hint(content, str(rec.get("relpath", "")))
            if hint.get("parse_uncertain"):
                parse_uncertain_files += 1
            java_hints.append(hint)
        elif bucket == "templates":
            template_scanned += 1
            rel = str(rec.get("relpath", ""))
            hits = [kw for kw in kws if kw and kw in rel.lower()]
            template_hints.append(
                {
                    "rel_path": rel,
                    "keyword_hits": hits,
                }
            )
            if kws:
                p = repo_root / rel
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    text = ""
                bytes_read += min(len(text.encode("utf-8", errors="ignore")), 8192)

    metrics = {
        "java_scanned": java_scanned,
        "template_scanned": template_scanned,
        "bytes_read": int(bytes_read),
        "parse_uncertain_files": int(parse_uncertain_files),
    }
    payload = {
        "version": SCAN_GRAPH_VERSION,
        "generated_at": utc_now_iso(),
        "repo_root": str(repo_root.resolve()),
        "file_index": file_index,
        "java_hints": java_hints,
        "template_hints": template_hints,
    }
    return payload, metrics


def build_scan_graph(
    *,
    repo_root: Path,
    roots: Optional[Iterable[str]] = None,
    max_files: Optional[int] = None,
    max_seconds: Optional[int] = None,
    keywords: Optional[List[str]] = None,
    cache_dir: Optional[Path] = None,
    producer_versions: Optional[dict] = None,
) -> dict:
    repo_root = Path(repo_root).resolve()
    roots_resolved = _resolve_roots(repo_root, roots)
    started = time.time()
    records, walk_stats = _iter_files(repo_root, roots_resolved, max_files=max_files, max_seconds=max_seconds)
    cache_key = _compute_cache_key(records, roots_resolved, max_files=max_files, max_seconds=max_seconds)

    cache_hit = False
    cache_hit_files = 0
    cache_miss_files = len(records)
    payload: dict
    parse_metrics = {"java_scanned": 0, "template_scanned": 0, "bytes_read": 0, "parse_uncertain_files": 0}

    cache_path = None
    if cache_dir is not None:
        cache_dir = Path(cache_dir).resolve()
        cache_path = cache_dir / f"{cache_key}.json"
        cached = load_json(cache_path)
        if cached.get("cache_key") == cache_key and isinstance(cached.get("file_index"), dict):
            payload = dict(cached)
            cache_hit = True
            cache_hit_files = len(records)
            cache_miss_files = 0
        else:
            payload, parse_metrics = _build_from_records(repo_root, records, keywords or [])
            payload["cache_key"] = cache_key
            payload["roots"] = [str(p) for p in roots_resolved]
            payload["limits"] = {"max_files": max_files, "max_seconds": max_seconds}
            payload["limits_hit"] = bool(walk_stats.get("limit_reason"))
            payload["limits_reason"] = str(walk_stats.get("limit_reason") or "")
            payload["cache_source"] = "miss"
            atomic_write_json(cache_path, payload)
    else:
        payload, parse_metrics = _build_from_records(repo_root, records, keywords or [])
        payload["cache_key"] = cache_key
        payload["roots"] = [str(p) for p in roots_resolved]
        payload["limits"] = {"max_files": max_files, "max_seconds": max_seconds}
        payload["limits_hit"] = bool(walk_stats.get("limit_reason"))
        payload["limits_reason"] = str(walk_stats.get("limit_reason") or "")
        payload["cache_source"] = "none"

    elapsed = round(time.time() - started, 4)
    io_stats = {
        "files_seen": int(walk_stats.get("files_seen", 0)),
        "files_indexed": int(walk_stats.get("files_indexed", 0)),
        "java_scanned": int(parse_metrics.get("java_scanned", 0)),
        "template_scanned": int(parse_metrics.get("template_scanned", 0)),
        "bytes_read": int(parse_metrics.get("bytes_read", 0)),
        "scan_time_s": elapsed,
        "cache_hit_files": int(cache_hit_files),
        "cache_miss_files": int(cache_miss_files),
        "cache_hit_rate": 1.0 if cache_hit else (float(cache_hit_files) / float(cache_hit_files + cache_miss_files) if (cache_hit_files + cache_miss_files) else 0.0),
        "parse_uncertain_files": int(parse_metrics.get("parse_uncertain_files", 0)),
    }
    payload["cache_key"] = cache_key
    payload["cache_source"] = "hit" if cache_hit else payload.get("cache_source", "none")
    payload["cache_path"] = str(cache_path) if cache_path else ""
    producer = _normalize_producer_versions(producer_versions)
    roots_rel = _roots_rel(repo_root, roots_resolved)
    payload["schema_version"] = SCAN_GRAPH_SCHEMA_VERSION
    payload["producer_versions"] = producer
    payload["roots_rel"] = roots_rel
    payload["graph_fingerprint"] = _compute_graph_fingerprint(
        payload.get("file_index", {}) if isinstance(payload.get("file_index"), dict) else {},
        roots_rel,
        producer,
    )
    payload["io_stats"] = io_stats
    return payload


def save_scan_graph(path: Path, payload: dict) -> None:
    atomic_write_json(path, payload)


def load_scan_graph(path: Path) -> dict:
    return load_json(path)


def _split_keywords(value: str) -> List[str]:
    if not value:
        return []
    return [x.strip() for x in str(value).split(",") if x.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build unified scan graph (v1)")
    parser.add_argument("--repo-root", required=True, help="Target repository root")
    parser.add_argument("--root", action="append", default=[], help="Optional scan root (absolute or repo-relative), repeatable")
    parser.add_argument("--workspace-root", default=None, help="Optional workspace root; output defaults to <workspace-root>/scan_graph/scan_graph.json")
    parser.add_argument("--cache-dir", default=None, help="Optional cache directory (default: <workspace-root>/scan_cache)")
    parser.add_argument("--out", default=None, help="Output scan_graph.json path")
    parser.add_argument("--keywords", default="", help="Comma-separated keywords for template hint matching")
    parser.add_argument("--max-files", type=int, default=None, help="Max files to index")
    parser.add_argument("--max-seconds", type=int, default=None, help="Max scan seconds")
    parser.add_argument("--read-only", action="store_true", help="Print graph JSON to stdout instead of writing file")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        print(f"FAIL: repo-root not found: {repo_root}", file=sys.stderr)
        return 1

    out_path: Optional[Path] = None
    workspace_root: Optional[Path] = None
    if args.workspace_root:
        workspace_root = Path(args.workspace_root).resolve()
    if args.out:
        out_path = Path(args.out).resolve()
    elif workspace_root is not None:
        out_path = workspace_root / "scan_graph" / "scan_graph.json"

    cache_dir = Path(args.cache_dir).resolve() if args.cache_dir else None
    if cache_dir is None and workspace_root is not None:
        cache_dir = workspace_root / "scan_cache"

    graph = build_scan_graph(
        repo_root=repo_root,
        roots=args.root or None,
        max_files=args.max_files,
        max_seconds=args.max_seconds,
        keywords=_split_keywords(args.keywords),
        cache_dir=cache_dir,
    )
    if args.read_only:
        print(json.dumps(graph, ensure_ascii=False))
        return 0
    if out_path is None:
        print("FAIL: --out or --workspace-root is required unless --read-only is used", file=sys.stderr)
        return 1
    save_scan_graph(out_path, graph)
    print(f"[scan_graph] output: {out_path}")
    print(f"[scan_graph] cache_key: {graph.get('cache_key', '')}")
    io = graph.get("io_stats", {}) if isinstance(graph.get("io_stats"), dict) else {}
    print(
        f"[scan_graph] io_stats: files_indexed={io.get('files_indexed', 0)} "
        f"java_scanned={io.get('java_scanned', 0)} "
        f"template_scanned={io.get('template_scanned', 0)} "
        f"bytes_read={io.get('bytes_read', 0)} "
        f"cache_hit_rate={io.get('cache_hit_rate', 0.0)} "
        f"scan_time_s={io.get('scan_time_s', 0.0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
