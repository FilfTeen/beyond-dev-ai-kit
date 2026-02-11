"""Federated capability index store helpers (Round23)."""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    import fcntl  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - non-posix fallback
    fcntl = None

MAX_RUNS_PER_REPO = 120


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(ts)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        tmp_path.replace(path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def atomic_append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    if fcntl is not None:
        with path.open("a", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        return

    lock_path = path.with_name(f"{path.name}.lock")
    lock_fd = None
    try:
        deadline = time.time() + 5.0
        while True:
            try:
                lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                break
            except FileExistsError:
                if time.time() >= deadline:
                    raise TimeoutError(f"timeout waiting for lock: {lock_path}")
                time.sleep(0.02)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
    finally:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass
        try:
            lock_path.unlink()
        except OSError:
            pass


def load_federated_index(path: str | Path) -> dict:
    index_path = Path(path)
    if not index_path.exists():
        return {"version": "1.0.0", "updated_at": utc_now_iso(), "repos": {}}
    try:
        loaded = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": "1.0.0", "updated_at": utc_now_iso(), "repos": {}}
    if not isinstance(loaded, dict):
        loaded = {}
    loaded.setdefault("version", "1.0.0")
    loaded.setdefault("updated_at", utc_now_iso())
    if not isinstance(loaded.get("repos"), dict):
        loaded["repos"] = {}
    return loaded


def save_federated_index(path: str | Path, data: dict) -> None:
    payload = dict(data or {})
    payload["version"] = "1.0.0"
    payload["updated_at"] = utc_now_iso()
    if not isinstance(payload.get("repos"), dict):
        payload["repos"] = {}
    atomic_write_json(Path(path), payload)


def confidence_tier_rank(tier: str) -> int:
    mapping = {"high": 3, "medium": 2, "low": 1}
    return mapping.get(str(tier or "").strip().lower(), 0)


def build_run_record(
    *,
    command: str,
    run_id: str,
    timestamp: str,
    workspace: str,
    latest_path: str,
    layout: str,
    metrics: dict,
    versions: dict,
    governance: dict,
) -> dict:
    limits = metrics.get("limits", {}) if isinstance(metrics.get("limits"), dict) else {}
    hint_bundle = metrics.get("hint_bundle", "") or ""
    return {
        "run_id": str(run_id),
        "timestamp": str(timestamp or utc_now_iso()),
        "command": str(command),
        "workspace": str(workspace),
        "latest_path": str(latest_path),
        "layout": str(layout or ""),
        "metrics": {
            "module_candidates": int(metrics.get("module_candidates", 0) or 0),
            "endpoints_total": int(metrics.get("endpoints_total", 0) or 0),
            "scan_time_s": float(metrics.get("scan_time_s", 0.0) or 0.0),
            "ambiguity_ratio": float(metrics.get("ambiguity_ratio", 0.0) or 0.0),
            "confidence_tier": str(metrics.get("confidence_tier", "") or ""),
            "limits_hit": bool(metrics.get("limits_hit", False)),
            "limits": {
                "max_files": limits.get("max_files"),
                "max_seconds": limits.get("max_seconds"),
                "reason_code": str(limits.get("reason_code", metrics.get("limits_reason_code", "-"))),
            },
            "layout": str(layout or ""),
            "hint_bundle_created": bool(metrics.get("hints_emitted", False)),
            "hint_bundle_kind": str(metrics.get("hint_bundle_kind", "") or ""),
            "hint_bundle_expires_at": str(metrics.get("hint_bundle_expires_at", "") or ""),
            "hint_bundle_path": str(hint_bundle),
            "hint_applied": bool(metrics.get("hint_applied", False)),
            "hint_verified": bool(metrics.get("hint_verified", False)),
            "hint_expired": bool(metrics.get("hint_expired", False)),
            "keywords": metrics.get("keywords_used", []) if isinstance(metrics.get("keywords_used"), list) else [],
            "endpoint_paths": metrics.get("endpoint_paths", []) if isinstance(metrics.get("endpoint_paths"), list) else [],
        },
        "versions": {
            "package": str(versions.get("package", "") or ""),
            "plugin": str(versions.get("plugin", "") or ""),
            "contract": str(versions.get("contract", "") or ""),
        },
        "governance": {
            "enabled": bool(governance.get("enabled", False)),
            "token_used": bool(governance.get("token_used", False)),
            "policy_hash": str(governance.get("policy_hash", "") or ""),
        },
    }


def update_federated_repo_entry(
    *,
    index: dict,
    repo_fp: str,
    repo_root: str,
    latest_pointer: dict,
    run_record: dict,
    governance: dict,
    versions: dict,
    max_runs: int = MAX_RUNS_PER_REPO,
) -> dict:
    repos = index.setdefault("repos", {})
    entry = repos.get(repo_fp, {})
    if not isinstance(entry, dict):
        entry = {}
    runs = entry.get("runs", [])
    if not isinstance(runs, list):
        runs = []
    runs.append(run_record)
    if len(runs) > int(max_runs):
        runs = runs[-int(max_runs):]
    entry.update(
        {
            "repo_fp": str(repo_fp),
            "repo_root": str(repo_root),
            "last_seen_at": str(run_record.get("timestamp", utc_now_iso())),
            "latest": latest_pointer if isinstance(latest_pointer, dict) else {},
            "runs": runs,
            "versions": {
                "package": str(versions.get("package", "") or ""),
                "plugin": str(versions.get("plugin", "") or ""),
                "contract": str(versions.get("contract", "") or ""),
            },
            "governance": {
                "enabled": bool(governance.get("enabled", False)),
                "token_used": bool(governance.get("token_used", False)),
                "policy_hash": str(governance.get("policy_hash", "") or ""),
            },
            "layout": str((run_record.get("layout") or "")),
            "metrics": run_record.get("metrics", {}),
        }
    )
    repos[repo_fp] = entry
    index["repos"] = repos
    return index


def write_repo_mirror(global_state_root: str | Path, repo_fp: str, entry: dict) -> Path:
    mirror_path = Path(global_state_root) / "repos" / str(repo_fp) / "index.json"
    atomic_write_json(mirror_path, entry if isinstance(entry, dict) else {})
    return mirror_path


def rank_query_runs(
    *,
    index: dict,
    keyword: str = "",
    endpoint: str = "",
    top_k: int = 10,
    strict_query: bool = False,
    include_limits_hit: bool = False,
) -> List[dict]:
    repos = index.get("repos", {})
    if not isinstance(repos, dict):
        return []
    key = str(keyword or "").strip().lower()
    ep = str(endpoint or "").strip().lower()
    ranked: List[dict] = []
    for repo_fp, entry in repos.items():
        if not isinstance(entry, dict):
            continue
        runs = entry.get("runs", [])
        if not isinstance(runs, list):
            continue
        for run in runs:
            if not isinstance(run, dict):
                continue
            metrics = run.get("metrics", {})
            if not isinstance(metrics, dict):
                metrics = {}
            limits_hit = bool(metrics.get("limits_hit", False))
            if strict_query and not include_limits_hit and limits_hit:
                continue
            endpoint_paths = metrics.get("endpoint_paths", [])
            if not isinstance(endpoint_paths, list):
                endpoint_paths = []
            keywords = metrics.get("keywords", [])
            if not isinstance(keywords, list):
                keywords = []
            command = str(run.get("command", "")).lower()
            layout = str(run.get("layout", ""))
            endpoint_match = 0
            keyword_match = 0
            if ep:
                endpoint_match = 1 if any(ep in str(p).lower() for p in endpoint_paths) else 0
            if key:
                keyword_match = 1 if any(key in str(k).lower() for k in keywords) else 0
                if not keyword_match:
                    keyword_match = 1 if key in command or key in layout else 0
            if ep and endpoint_match == 0:
                continue
            if key and keyword_match == 0 and not ep:
                continue
            ts = parse_iso_ts(str(run.get("timestamp", "")))
            recency = ts.timestamp() if ts else 0.0
            ambiguity = float(metrics.get("ambiguity_ratio", 1.0) or 1.0)
            conf_rank = confidence_tier_rank(str(metrics.get("confidence_tier", "")))
            ranked.append(
                {
                    "repo_fp": str(repo_fp),
                    "repo_root": str(entry.get("repo_root", "")),
                    "run": run,
                    "score": (
                        endpoint_match,
                        keyword_match,
                        recency,
                        -ambiguity,
                        conf_rank,
                    ),
                }
            )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[: max(1, int(top_k))]
