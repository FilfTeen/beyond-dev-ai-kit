"""Hint bundle helpers for profile_delta assetization (Round22)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

HINT_BUNDLE_VERSION = "1.0.0"
HINT_BUNDLE_KIND_PROFILE_DELTA = "profile_delta"


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
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def normalize_scope(scope_value: Any) -> List[str]:
    if scope_value is None:
        return ["*"]
    if isinstance(scope_value, str):
        values = [x.strip().lower() for x in scope_value.split(",") if x.strip()]
        return values or ["*"]
    if isinstance(scope_value, list):
        values = [str(x).strip().lower() for x in scope_value if str(x).strip()]
        return values or ["*"]
    return ["*"]


def _parse_legacy_hint_yaml(content: str) -> dict:
    identity = {"backend_package_hint": "", "web_path_hint": "", "keywords": []}
    in_keywords = False
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("backend_package_hint:"):
            identity["backend_package_hint"] = line.split(":", 1)[1].strip().strip("\"'")
            in_keywords = False
            continue
        if line.startswith("web_path_hint:"):
            identity["web_path_hint"] = line.split(":", 1)[1].strip().strip("\"'")
            in_keywords = False
            continue
        if line.startswith("keywords:"):
            in_keywords = True
            continue
        if in_keywords and line.startswith("-"):
            kw = line[1:].strip().strip("\"'")
            if kw:
                identity["keywords"].append(kw)
            continue
        in_keywords = False
    return {
        "version": HINT_BUNDLE_VERSION,
        "kind": HINT_BUNDLE_KIND_PROFILE_DELTA,
        "created_at": utc_now_iso(),
        "scope": ["discover", "hint_bundle"],
        "repo_fingerprint": "",
        "delta": {
            "identity": identity,
            "roots": {"backend_java": [], "web_template": []},
            "layout": {"layout": "", "adapter_used": ""},
        },
        "_legacy_yaml": True,
    }


def load_hint_bundle_input(raw: str) -> dict:
    value = str(raw or "").strip()
    result = {
        "ok": False,
        "error": "empty",
        "source_type": "",
        "source_path": "",
        "payload": {},
    }
    if not value:
        return result

    source_path = Path(value).expanduser()
    if source_path.exists() and source_path.is_file():
        text = source_path.read_text(encoding="utf-8", errors="ignore")
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                result.update(
                    {
                        "ok": True,
                        "error": "",
                        "source_type": "path",
                        "source_path": str(source_path.resolve()),
                        "payload": payload,
                    }
                )
                return result
        except json.JSONDecodeError:
            payload = _parse_legacy_hint_yaml(text)
            result.update(
                {
                    "ok": True,
                    "error": "",
                    "source_type": "path",
                    "source_path": str(source_path.resolve()),
                    "payload": payload,
                }
            )
            return result
        result["error"] = "invalid_bundle_json_file"
        return result

    try:
        payload = json.loads(value)
        if isinstance(payload, dict):
            result.update(
                {
                    "ok": True,
                    "error": "",
                    "source_type": "inline_json",
                    "source_path": "",
                    "payload": payload,
                }
            )
            return result
    except json.JSONDecodeError:
        pass

    result["error"] = "not_a_file_or_inline_json"
    return result


def build_profile_delta_bundle(
    *,
    repo_fingerprint: str,
    run_id: str,
    calibration_report: dict,
    hint_identity: dict,
    layout_hints: dict,
    roots_hints: dict,
    ttl_seconds: int,
) -> dict:
    created_at = utc_now_iso()
    expires_at = ""
    if int(ttl_seconds) > 0:
        dt = parse_iso_ts(created_at)
        if dt:
            expires_at = datetime.fromtimestamp(
                dt.timestamp() + int(ttl_seconds), tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "version": HINT_BUNDLE_VERSION,
        "kind": HINT_BUNDLE_KIND_PROFILE_DELTA,
        "created_at": created_at,
        "expires_at": expires_at,
        "ttl_seconds": int(ttl_seconds),
        "repo_fingerprint": str(repo_fingerprint),
        "scope": ["discover", "hint_bundle"],
        "source": {
            "run_id": str(run_id),
            "command": "discover",
            "needs_human_hint": bool(calibration_report.get("needs_human_hint", False)),
            "confidence": float(calibration_report.get("confidence", 0.0) or 0.0),
            "confidence_tier": str(calibration_report.get("confidence_tier", "low")),
            "reasons": calibration_report.get("reasons", []) if isinstance(calibration_report.get("reasons"), list) else [],
        },
        "delta": {
            "identity": {
                "backend_package_hint": str(hint_identity.get("backend_package_hint", "") or ""),
                "web_path_hint": str(hint_identity.get("web_path_hint", "") or ""),
                "keywords": hint_identity.get("keywords", []) if isinstance(hint_identity.get("keywords"), list) else [],
            },
            "roots": {
                "backend_java": roots_hints.get("backend_java", []) if isinstance(roots_hints.get("backend_java"), list) else [],
                "web_template": roots_hints.get("web_template", []) if isinstance(roots_hints.get("web_template"), list) else [],
            },
            "layout": {
                "layout": str(layout_hints.get("layout", "") or ""),
                "adapter_used": str(layout_hints.get("adapter_used", "") or ""),
            },
        },
    }


def verify_hint_bundle(
    payload: dict,
    *,
    repo_fingerprint: str,
    command: str,
    allow_cross_repo_hints: bool,
) -> dict:
    result = {
        "ok": False,
        "verified": False,
        "expired": False,
        "error": "",
        "kind": "",
        "created_at": "",
        "expires_at": "",
        "ttl_seconds": 0,
        "repo_fingerprint": "",
        "scope": [],
        "identity": {"backend_package_hint": "", "web_path_hint": "", "keywords": []},
        "roots_hints": {"backend_java": [], "web_template": []},
        "layout_hints": {"layout": "", "adapter_used": ""},
    }
    if not isinstance(payload, dict):
        result["error"] = "payload_not_object"
        return result

    kind = str(payload.get("kind", HINT_BUNDLE_KIND_PROFILE_DELTA) or HINT_BUNDLE_KIND_PROFILE_DELTA)
    result["kind"] = kind
    if kind != HINT_BUNDLE_KIND_PROFILE_DELTA:
        result["error"] = "unsupported_kind"
        return result

    created_at = str(payload.get("created_at", "") or "")
    expires_at = str(payload.get("expires_at", "") or "")
    ttl_seconds = payload.get("ttl_seconds", 0)
    try:
        ttl_seconds_i = int(ttl_seconds)
    except (TypeError, ValueError):
        result["error"] = "invalid_ttl_seconds"
        return result
    result["created_at"] = created_at
    result["expires_at"] = expires_at
    result["ttl_seconds"] = ttl_seconds_i

    now = datetime.now(timezone.utc)
    expiry = None
    if expires_at:
        expiry = parse_iso_ts(expires_at)
        if not expiry:
            result["error"] = "invalid_expires_at"
            return result
    elif ttl_seconds_i > 0:
        created_dt = parse_iso_ts(created_at)
        if not created_dt:
            result["error"] = "missing_or_invalid_created_at_for_ttl"
            return result
        expiry = datetime.fromtimestamp(created_dt.timestamp() + ttl_seconds_i, tz=timezone.utc)
        result["expires_at"] = expiry.strftime("%Y-%m-%dT%H:%M:%SZ")
    if expiry and now > expiry:
        result["expired"] = True
        result["error"] = "hint_bundle_expired"
        return result

    bundle_fp = str(payload.get("repo_fingerprint", "") or "")
    result["repo_fingerprint"] = bundle_fp
    if not allow_cross_repo_hints and bundle_fp and bundle_fp != str(repo_fingerprint):
        result["error"] = "repo_fingerprint_mismatch"
        return result

    scope = normalize_scope(payload.get("scope"))
    result["scope"] = scope
    cmd = str(command or "").strip().lower()
    if "*" not in scope and cmd not in scope:
        result["error"] = "hint_scope_mismatch"
        return result

    delta = payload.get("delta", {})
    if not isinstance(delta, dict):
        delta = {}
    identity = delta.get("identity", {})
    if not isinstance(identity, dict):
        identity = {}
    keywords = identity.get("keywords", [])
    if isinstance(keywords, str):
        keywords = [x.strip() for x in keywords.split(",") if x.strip()]
    if not isinstance(keywords, list):
        keywords = []
    keywords = [str(x).strip() for x in keywords if str(x).strip()]

    roots = delta.get("roots", {})
    if not isinstance(roots, dict):
        roots = {}
    backend_java = roots.get("backend_java", [])
    if not isinstance(backend_java, list):
        backend_java = []
    web_template = roots.get("web_template", [])
    if not isinstance(web_template, list):
        web_template = []

    layout = delta.get("layout", {})
    if not isinstance(layout, dict):
        layout = {}

    result["identity"] = {
        "backend_package_hint": str(identity.get("backend_package_hint", "") or ""),
        "web_path_hint": str(identity.get("web_path_hint", "") or ""),
        "keywords": keywords,
    }
    result["roots_hints"] = {
        "backend_java": [str(x).strip() for x in backend_java if str(x).strip()],
        "web_template": [str(x).strip() for x in web_template if str(x).strip()],
    }
    result["layout_hints"] = {
        "layout": str(layout.get("layout", "") or ""),
        "adapter_used": str(layout.get("adapter_used", "") or ""),
    }
    result["ok"] = True
    result["verified"] = True
    return result

