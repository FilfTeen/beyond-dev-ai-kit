"""Capability registry persistence helpers (atomic JSON writes)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def load_capability_index(path: str | Path) -> dict:
    index_path = Path(path)
    if not index_path.exists():
        return {"version": "1.0.0", "updated_at": _utc_now_iso(), "projects": {}}
    try:
        loaded = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": "1.0.0", "updated_at": _utc_now_iso(), "projects": {}}

    if not isinstance(loaded, dict):
        loaded = {}
    loaded.setdefault("version", "1.0.0")
    loaded.setdefault("updated_at", _utc_now_iso())
    if not isinstance(loaded.get("projects"), dict):
        loaded["projects"] = {}
    return loaded


def save_capability_index(path: str | Path, data: dict) -> None:
    index_path = Path(path)
    data = dict(data or {})
    data["version"] = "1.0.0"
    data["updated_at"] = _utc_now_iso()
    if not isinstance(data.get("projects"), dict):
        data["projects"] = {}
    _atomic_write_json(index_path, data)


def update_project_entry(index: dict, fp: str, entry_patch: dict) -> dict:
    projects = index.setdefault("projects", {})
    current = projects.get(fp, {})
    if not isinstance(current, dict):
        current = {}
    current.update(entry_patch or {})
    projects[fp] = current
    index["projects"] = projects
    return index


def write_latest_pointer(global_state_root: str | Path, fp: str, run_id: str, workspace_path: str) -> Path:
    latest_dir = Path(global_state_root) / fp
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest_path = latest_dir / "latest.json"
    latest_payload = {
        "fingerprint": fp,
        "run_id": run_id,
        "workspace": workspace_path,
        "timestamp": _utc_now_iso(),
    }
    _atomic_write_json(latest_path, latest_payload)
    return latest_path

