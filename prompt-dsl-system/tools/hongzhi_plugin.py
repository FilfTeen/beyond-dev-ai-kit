#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Hongzhi AI-Kit Plugin Runner
Version: 1.1.0 (R17 Packaging + Agent Contract v4)

Role:
  1. Standardization: unified entry point for all dsl-tools.
  2. Governance: allowlist/denylist checks, read-only enforcement.
  3. Observability: capabilities.json output for Agent consumption.
  4. Isolation: workspace-based execution.
"""

import sys
import os
import argparse
import json
import time
import hashlib
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from hongzhi_ai_kit import __version__ as PACKAGE_VERSION
except Exception:
    PACKAGE_VERSION = "unknown"

from hongzhi_ai_kit.capability_store import (
    load_capability_index,
    save_capability_index,
    update_project_entry,
    write_latest_pointer,
)
from hongzhi_ai_kit.hint_bundle import (
    HINT_BUNDLE_KIND_PROFILE_DELTA,
    build_profile_delta_bundle,
    load_hint_bundle_input,
    verify_hint_bundle,
    atomic_write_json as hint_atomic_write_json,
)
from hongzhi_ai_kit.federated_store import (
    load_federated_index,
    save_federated_index,
    build_run_record,
    update_federated_repo_entry,
    write_repo_mirror,
    rank_query_runs,
    atomic_append_jsonl,
)
from hongzhi_ai_kit.paths import resolve_global_state_root, resolve_workspace_root
from scan_graph import (
    SCAN_GRAPH_SCHEMA_VERSION,
    analyze_scan_graph_payload,
    build_scan_graph,
    load_scan_graph,
    save_scan_graph,
)

# ═══════════════════════════════════════════════════════════════════════════════
#  Configuration & Constants
# ═══════════════════════════════════════════════════════════════════════════════

PLUGIN_VERSION = "1.1.0"
CONTRACT_VERSION = "1.1.0"
SUMMARY_VERSION = "3.0"
GOVERNANCE_ENV = "HONGZHI_PLUGIN_ENABLE"
GOVERNANCE_EXIT_CODE = 10
GOVERNANCE_DENY_EXIT_CODE = 11
GOVERNANCE_ALLOW_EXIT_CODE = 12
POLICY_PARSE_EXIT_CODE = 13
COMPANY_SCOPE_EXIT_CODE = 26
LIMIT_EXIT_CODE = 20
CALIBRATION_EXIT_CODE = 21
HINT_VERIFY_EXIT_CODE = 22
HINT_SCOPE_EXIT_CODE = 23
INDEX_SCOPE_EXIT_CODE = 24
SCAN_GRAPH_MISMATCH_EXIT_CODE = 25
MACHINE_JSON_ENV = "HONGZHI_MACHINE_JSON_ENABLE"
MACHINE_JSON_CLI_DEFAULT = "1"
COMPANY_SCOPE_ENV = "HONGZHI_COMPANY_SCOPE"
COMPANY_SCOPE_REQUIRE_ENV = "HONGZHI_REQUIRE_COMPANY_SCOPE"
COMPANY_SCOPE_DEFAULT = "hongzhi-work-dev"
GLOBAL_STATE_ENV = "HONGZHI_PLUGIN_GLOBAL_STATE_ROOT"
HINT_BUNDLE_VERSION = "1.0.0"
MISMATCH_REASON_ALLOWED = {
    "schema_version_mismatch",
    "producer_version_mismatch",
    "fingerprint_mismatch",
    "corrupted_cache",
    "unknown",
}
MISMATCH_REASON_SUGGESTIONS = {
    "schema_version_mismatch": "clear scan_cache and rerun discover with current plugin",
    "producer_version_mismatch": "rerun discover to rebuild scan graph with matching versions",
    "fingerprint_mismatch": "disable smart reuse or rerun discover without cached graph",
    "corrupted_cache": "delete scan_cache files and rerun discover",
    "unknown": "rerun discover --strict and inspect scan_graph_spot_check details",
}
MACHINE_JSON_ENABLED_RUNTIME = True
COMPANY_SCOPE_RUNTIME = COMPANY_SCOPE_DEFAULT
COMPANY_SCOPE_REQUIRED_RUNTIME = False

SNAPSHOT_EXCLUDES = {
    ".git", ".idea", ".DS_Store", "target", "build", "node_modules",
    "__pycache__", ".gradle", ".mvn", "dist", "out"
}
SNAPSHOT_EXT_EXCLUDES = {
    ".class", ".jar", ".war", ".ear", ".zip", ".tar.gz", ".pyc"
}

SCRIPT_DIR = Path(__file__).resolve().parent


# ═══════════════════════════════════════════════════════════════════════════════
#  Shared helpers
# ═══════════════════════════════════════════════════════════════════════════════

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S%fZ")


def version_triplet() -> dict:
    return {
        "package_version": PACKAGE_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "contract_version": CONTRACT_VERSION,
    }


def quote_machine_value(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def machine_json_field(
    *,
    path_value: str | Path,
    command: str,
    repo_fingerprint: str,
    run_id: str,
    extra: Optional[dict] = None,
) -> str:
    versions = version_triplet()
    payload = {
        "path": str(Path(path_value).expanduser().resolve()),
        "command": str(command or "-"),
        "versions": {
            "package": versions["package_version"],
            "plugin": versions["plugin_version"],
            "contract": versions["contract_version"],
        },
        "company_scope": str(company_scope_runtime()),
        "repo_fingerprint": str(repo_fingerprint or "-"),
        "run_id": str(run_id or "-"),
    }
    if isinstance(extra, dict):
        for key, value in extra.items():
            if value is None:
                continue
            payload[str(key)] = value
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
    # Keep single-token shell-friendly field: json='<one-line-json>'
    encoded = encoded.replace("'", "\\u0027")
    return f"'{encoded}'"


def parse_bool_switch(value: Any, default: bool = True) -> bool:
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if text in {"1", "true", "on", "yes"}:
        return True
    if text in {"0", "false", "off", "no"}:
        return False
    return bool(default)


def set_machine_json_runtime(cli_value: Any = None) -> None:
    global MACHINE_JSON_ENABLED_RUNTIME
    env_value = os.environ.get(MACHINE_JSON_ENV)
    if env_value is not None:
        MACHINE_JSON_ENABLED_RUNTIME = parse_bool_switch(env_value, default=True)
        return
    MACHINE_JSON_ENABLED_RUNTIME = parse_bool_switch(
        cli_value if cli_value is not None else MACHINE_JSON_CLI_DEFAULT,
        default=True,
    )


def machine_json_enabled() -> bool:
    return bool(MACHINE_JSON_ENABLED_RUNTIME)


def set_company_scope_runtime(args: argparse.Namespace) -> None:
    global COMPANY_SCOPE_RUNTIME
    global COMPANY_SCOPE_REQUIRED_RUNTIME

    env_scope = os.environ.get(COMPANY_SCOPE_ENV)
    cli_scope = getattr(args, "company_scope", COMPANY_SCOPE_DEFAULT)
    scope_value = str(env_scope if env_scope is not None else cli_scope).strip() or COMPANY_SCOPE_DEFAULT
    COMPANY_SCOPE_RUNTIME = scope_value

    env_required = os.environ.get(COMPANY_SCOPE_REQUIRE_ENV)
    cli_required = getattr(args, "require_company_scope", "0")
    if env_required is not None:
        COMPANY_SCOPE_REQUIRED_RUNTIME = parse_bool_switch(env_required, default=False)
    else:
        COMPANY_SCOPE_REQUIRED_RUNTIME = parse_bool_switch(cli_required, default=False)


def company_scope_runtime() -> str:
    return str(COMPANY_SCOPE_RUNTIME or COMPANY_SCOPE_DEFAULT)


def company_scope_required_runtime() -> bool:
    return bool(COMPANY_SCOPE_REQUIRED_RUNTIME)


def check_company_scope_gate(command: str) -> Tuple[bool, int, str]:
    if not company_scope_required_runtime():
        return True, 0, "company_scope_not_required"
    actual = company_scope_runtime()
    expected = COMPANY_SCOPE_DEFAULT
    if actual == expected:
        return True, 0, "company_scope_matched"
    return (
        False,
        COMPANY_SCOPE_EXIT_CODE,
        f"company_scope mismatch: expected={expected}, actual={actual}, command={command}",
    )


def normalize_mismatch_reason(value: Any) -> str:
    text = str(value or "").strip()
    if text not in MISMATCH_REASON_ALLOWED:
        return "unknown"
    return text


def mismatch_suggestion_for(reason: Any) -> str:
    normalized = normalize_mismatch_reason(reason)
    return str(MISMATCH_REASON_SUGGESTIONS.get(normalized, MISMATCH_REASON_SUGGESTIONS["unknown"]))


def canonical_path(path_value: str | Path) -> Path:
    return Path(path_value).expanduser().resolve()


def is_path_within(path_value: str | Path, root_value: str | Path) -> bool:
    path_obj = canonical_path(path_value)
    root_obj = canonical_path(root_value)
    if path_obj == root_obj:
        return True
    return root_obj in path_obj.parents


def normalize_scope(scope_value: Any) -> List[str]:
    if scope_value is None:
        return ["*"]
    if isinstance(scope_value, str):
        scope_items = [x.strip().lower() for x in scope_value.split(",") if x.strip()]
        return scope_items or ["*"]
    if isinstance(scope_value, list):
        normalized = []
        for item in scope_value:
            if isinstance(item, str) and item.strip():
                normalized.append(item.strip().lower())
        return normalized or ["*"]
    return ["*"]


def parse_permit_token(raw_token: str | None) -> dict:
    payload = {
        "provided": bool(raw_token and raw_token.strip()),
        "raw": (raw_token or "").strip(),
        "token": "",
        "scope": ["*"],
        "expires_at": None,
        "issued_at": None,
        "ttl_seconds": None,
        "valid": False,
        "reason": "token_not_provided",
    }
    if not payload["provided"]:
        return payload

    raw = payload["raw"]
    token_obj = None
    if raw.startswith("{") and raw.endswith("}"):
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                token_obj = loaded
        except json.JSONDecodeError:
            token_obj = None

    if token_obj is None:
        payload["token"] = raw
        payload["scope"] = ["*"]
        payload["valid"] = True
        payload["reason"] = "plain_token"
        return payload

    payload["token"] = str(token_obj.get("token") or token_obj.get("value") or "").strip()
    payload["scope"] = normalize_scope(token_obj.get("scope"))
    payload["expires_at"] = token_obj.get("expires_at")
    payload["issued_at"] = token_obj.get("issued_at") or token_obj.get("created_at")
    payload["ttl_seconds"] = token_obj.get("ttl_seconds")
    if not payload["token"]:
        payload["reason"] = "token_missing_value"
        return payload
    payload["valid"] = True
    payload["reason"] = "json_token"
    return payload


def validate_permit_token(parsed: dict, command: str) -> Tuple[bool, str]:
    if not parsed.get("provided"):
        return False, "token_not_provided"
    if not parsed.get("valid"):
        return False, parsed.get("reason", "token_invalid")

    now = datetime.now(timezone.utc)
    expires_at = parsed.get("expires_at")
    if expires_at:
        exp = parse_iso_ts(str(expires_at))
        if not exp:
            return False, "token_invalid_expires_at"
        if now > exp:
            return False, "token_expired"

    ttl_seconds = parsed.get("ttl_seconds")
    if ttl_seconds is not None:
        try:
            ttl = int(ttl_seconds)
        except (TypeError, ValueError):
            return False, "token_invalid_ttl"
        if ttl < 0:
            return False, "token_invalid_ttl"
        issued_at = parsed.get("issued_at")
        if not issued_at:
            return False, "token_missing_issued_at_for_ttl"
        issued = parse_iso_ts(str(issued_at))
        if not issued:
            return False, "token_invalid_issued_at"
        if (now - issued).total_seconds() > ttl:
            return False, "token_expired"

    scope = normalize_scope(parsed.get("scope"))
    command_l = (command or "").strip().lower()
    if "*" not in scope and command_l not in scope:
        return False, "token_scope_mismatch"
    return True, "token_valid"


def compute_policy_hash(policy: dict) -> str:
    fed_policy = policy.get("federated_index", {}) if isinstance(policy.get("federated_index"), dict) else {}
    canonical = {
        "enabled": bool(policy.get("enabled")),
        "allow_roots": sorted(str(x) for x in (policy.get("allow_roots") or [])),
        "deny_roots": sorted(str(x) for x in (policy.get("deny_roots") or [])),
        "permit_token_file": str(policy.get("permit_token_file") or ""),
        "federated_index_enabled": fed_policy.get("enabled"),
        "federated_index_write_jsonl": bool(fed_policy.get("write_jsonl", True)),
        "federated_index_write_repo_mirror": bool(fed_policy.get("write_repo_mirror", True)),
    }
    encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def build_scan_stats(metrics: dict) -> dict:
    cache_hit_files = as_int(metrics.get("cache_hit_files", 0), 0)
    cache_miss_files = as_int(metrics.get("cache_miss_files", 0), 0)
    files_scanned = as_int(metrics.get("files_scanned", metrics.get("total_scanned_files", cache_hit_files + cache_miss_files)), 0)
    return {
        "files_scanned": files_scanned,
        "cache_hit_files": cache_hit_files,
        "cache_miss_files": cache_miss_files,
        "cache_hit_rate": float(metrics.get("cache_hit_rate", 0.0) or 0.0),
    }


def evaluate_limits(args, metrics: dict, elapsed_s: float) -> Tuple[bool, List[str], List[str]]:
    scan_stats = build_scan_stats(metrics)
    metrics["scan_stats"] = scan_stats
    max_files = args.max_files if args.max_files is not None else None
    max_seconds = args.max_seconds if args.max_seconds is not None else None
    metrics["limits"] = {"max_files": max_files, "max_seconds": max_seconds}

    reason_codes: List[str] = []
    reason_texts: List[str] = []
    if max_files is not None and scan_stats["files_scanned"] > int(max_files):
        reason_codes.append("max_files")
        reason_texts.append(f"files_scanned={scan_stats['files_scanned']} exceeds max_files={int(max_files)}")
    if max_seconds is not None and float(elapsed_s) > float(max_seconds):
        reason_codes.append("max_seconds")
        reason_texts.append(f"scan_time_s={elapsed_s:.3f} exceeds max_seconds={float(max_seconds):.3f}")

    limits_hit = bool(reason_codes)
    metrics["limits_hit"] = limits_hit
    metrics["limits_reason"] = "; ".join(reason_texts) if reason_texts else ""
    metrics["limits_reason_code"] = ",".join(reason_codes) if reason_codes else "-"
    return limits_hit, reason_codes, reason_texts


def build_limits_suggestion(reason_codes: List[str], command: str, keywords_used: List[str]) -> str:
    if not reason_codes:
        return ""
    suggestions: List[str] = []
    if "max_files" in reason_codes:
        suggestions.append("increase --max-files")
    if "max_seconds" in reason_codes:
        suggestions.append("increase --max-seconds")
    if command == "discover" and not keywords_used:
        suggestions.append("provide --keywords to narrow scan scope")
    if command == "discover":
        suggestions.append("enable --smart for incremental reuse")
    deduped = []
    seen = set()
    for item in suggestions:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return "; ".join(deduped)


def default_hint_state(apply_hints_path: str = "", strategy: str = "conservative") -> dict:
    return {
        "emitted": False,
        "applied": False,
        "bundle_path": "",
        "source_path": str(apply_hints_path or ""),
        "strategy": str(strategy or "conservative"),
        "verified": False,
        "expired": False,
        "effective": False,
        "confidence_delta": 0.0,
        "ttl_seconds": 0,
        "created_at": "",
        "expires_at": "",
        "kind": "",
        "identity": {
            "backend_package_hint": "",
            "web_path_hint": "",
            "keywords": [],
        },
        "roots_hints": {
            "backend_java": [],
            "web_template": [],
        },
        "layout_hints": {
            "layout": "",
            "adapter_used": "",
        },
    }


def default_hint_bundle_info() -> dict:
    return {
        "kind": "",
        "path": "",
        "verified": False,
        "expired": False,
        "ttl_seconds": 0,
        "created_at": "",
        "expires_at": "",
    }


def merge_keywords(base_keywords: List[str], hint_keywords: List[str], strategy: str) -> List[str]:
    base = [str(k).strip() for k in (base_keywords or []) if str(k).strip()]
    hinted = [str(k).strip() for k in (hint_keywords or []) if str(k).strip()]
    if not hinted:
        return base

    merged: List[str] = []
    if strategy == "aggressive":
        ordered = hinted + base
    else:
        ordered = base + hinted
    seen = set()
    for kw in ordered:
        low = kw.lower()
        if low in seen:
            continue
        seen.add(low)
        merged.append(kw)
    return merged


def apply_hint_boost_to_candidates(candidates: List[dict], hint_identity: dict, strategy: str) -> List[dict]:
    if not candidates:
        return []
    backend_hint = str(hint_identity.get("backend_package_hint", "") or "").strip().lower()
    hint_keywords = [str(x).strip().lower() for x in hint_identity.get("keywords", []) if str(x).strip()]
    mode = "aggressive" if strategy == "aggressive" else "conservative"
    boosted: List[dict] = []

    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        c = dict(cand)
        score = float(c.get("score", 0.0) or 0.0)
        module_key = str(c.get("module_key", "") or "").strip().lower()
        package_prefix = str(c.get("package_prefix", "") or "").strip().lower()
        eff = score

        if backend_hint:
            if package_prefix == backend_hint or package_prefix.startswith(backend_hint + ".") or package_prefix.startswith(backend_hint):
                eff *= 2.8 if mode == "aggressive" else 1.8
            elif backend_hint.startswith(package_prefix + "."):
                eff *= 1.3 if mode == "aggressive" else 1.15

        for kw in hint_keywords:
            if not kw:
                continue
            if module_key == kw:
                eff *= 1.9 if mode == "aggressive" else 1.3
            elif kw in module_key:
                eff *= 1.4 if mode == "aggressive" else 1.15

        c["_hint_effective_score"] = round(eff, 6)
        c["score"] = round(eff, 2)
        boosted.append(c)

    boosted.sort(key=lambda item: float(item.get("_hint_effective_score", 0.0) or 0.0), reverse=True)
    for item in boosted:
        item.pop("_hint_effective_score", None)
    return boosted


def emit_hint_bundle(
    workspace: Path,
    command: str,
    repo_fingerprint: str,
    run_id: str,
    calibration_report: dict,
    hint_state: dict,
    hint_bundle_info: dict,
    emit_hints: bool,
    ttl_seconds: int,
) -> str:
    should_emit = bool(metrics_bool(calibration_report.get("needs_human_hint", False)) or emit_hints)
    if not should_emit:
        return ""
    if command != "discover":
        return ""
    if not isinstance(calibration_report, dict):
        return ""

    discover_dir = workspace / "discover"
    discover_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = discover_dir / "hints.json"
    identity = calibration_report.get("suggested_hints", {}).get("identity", {})
    if not isinstance(identity, dict):
        identity = hint_state.get("identity", {}) if isinstance(hint_state.get("identity"), dict) else {}

    roots_hints = hint_state.get("roots_hints", {}) if isinstance(hint_state.get("roots_hints"), dict) else {}
    layout_hints = hint_state.get("layout_hints", {}) if isinstance(hint_state.get("layout_hints"), dict) else {}
    payload = build_profile_delta_bundle(
        repo_fingerprint=repo_fingerprint,
        run_id=run_id,
        calibration_report=calibration_report,
        hint_identity=identity,
        layout_hints=layout_hints,
        roots_hints=roots_hints,
        ttl_seconds=int(ttl_seconds),
    )
    payload["rerun"] = {
        "hint_strategy_default": str(hint_state.get("strategy", "conservative")),
        "command_template": f"hongzhi-ai-kit discover --repo-root <repo_root> --apply-hints {bundle_path.resolve()}",
    }
    hint_atomic_write_json(bundle_path, payload)
    hint_bundle_info.update(
        {
            "kind": HINT_BUNDLE_KIND_PROFILE_DELTA,
            "path": str(bundle_path.resolve()),
            "verified": True,
            "expired": False,
            "ttl_seconds": int(payload.get("ttl_seconds", 0) or 0),
            "created_at": str(payload.get("created_at", "") or ""),
            "expires_at": str(payload.get("expires_at", "") or ""),
        }
    )
    return str(bundle_path.resolve())


def print_hints_pointer_line(
    hints_path: str,
    *,
    command: str = "-",
    repo_fingerprint: str = "-",
    run_id: str = "-",
) -> None:
    versions = version_triplet()
    resolved = Path(hints_path).resolve()
    json_field = machine_json_field(
        path_value=resolved,
        command=command,
        repo_fingerprint=repo_fingerprint,
        run_id=run_id,
    )
    json_part = f"json={json_field} " if machine_json_enabled() else ""
    print(
        f"HONGZHI_HINTS {resolved} "
        f"path={quote_machine_value(str(resolved))} "
        f"{json_part}"
        f"company_scope={quote_machine_value(company_scope_runtime())} "
        f"package_version={versions['package_version']} "
        f"plugin_version={versions['plugin_version']} "
        f"contract_version={versions['contract_version']}"
    )


def print_hints_block_line(code: int, reason: str, command: str, detail: str, token_scope: list | None) -> None:
    versions = version_triplet()
    scope_text = ",".join(token_scope or ["*"])
    json_field = machine_json_field(
        path_value="-",
        command=command,
        repo_fingerprint="-",
        run_id="-",
        extra={
            "code": int(code),
            "reason": str(reason),
            "scope": scope_text,
            "detail": str(detail),
        },
    )
    json_part = f"json={json_field} " if machine_json_enabled() else ""
    print(
        f"HONGZHI_HINTS_BLOCK code={int(code)} reason={reason} command={command} "
        f"scope={scope_text} "
        f"{json_part}"
        f"company_scope={quote_machine_value(company_scope_runtime())} "
        f"package_version={versions['package_version']} "
        f"plugin_version={versions['plugin_version']} "
        f"contract_version={versions['contract_version']} "
        f"detail={quote_machine_value(detail)}"
    )


def hint_bundle_scope_allowed(governance: dict) -> Tuple[bool, str]:
    if not isinstance(governance, dict):
        return False, "governance_missing"
    if not governance.get("token_used", False):
        return True, "allowed"
    scope = normalize_scope(governance.get("token_scope"))
    if "*" in scope or "hint_bundle" in scope:
        return True, "allowed"
    return False, "token_scope_missing"


def print_index_pointer_line(
    index_path: Path,
    *,
    command: str = "-",
    repo_fingerprint: str = "-",
    run_id: str = "-",
    mismatch_reason: str = "-",
    mismatch_detail: str = "-",
    mismatch_suggestion: str = "-",
) -> None:
    versions = version_triplet()
    resolved = index_path.resolve()
    json_field = machine_json_field(
        path_value=resolved,
        command=command,
        repo_fingerprint=repo_fingerprint,
        run_id=run_id,
        extra={
            "mismatch_reason": str(mismatch_reason or "-"),
            "mismatch_detail": str(mismatch_detail or "-"),
            "mismatch_suggestion": str(mismatch_suggestion or "-"),
        },
    )
    json_part = f"json={json_field} " if machine_json_enabled() else ""
    print(
        f"HONGZHI_INDEX {resolved} "
        f"path={quote_machine_value(str(resolved))} "
        f"{json_part}"
        f"mismatch_reason={str(mismatch_reason or '-')} "
        f"mismatch_detail={quote_machine_value(str(mismatch_detail or '-'))} "
        f"mismatch_suggestion={quote_machine_value(str(mismatch_suggestion or '-'))} "
        f"company_scope={quote_machine_value(company_scope_runtime())} "
        f"package_version={versions['package_version']} "
        f"plugin_version={versions['plugin_version']} "
        f"contract_version={versions['contract_version']}"
    )


def print_index_block_line(
    code: int,
    reason: str,
    command: str,
    detail: str,
    token_scope: list | None,
    required_scope: str = "federated_index",
) -> None:
    versions = version_triplet()
    scope_text = str(required_scope or "federated_index")
    token_scope_text = ",".join(token_scope or ["*"])
    json_field = machine_json_field(
        path_value="-",
        command=command,
        repo_fingerprint="-",
        run_id="-",
        extra={
            "code": int(code),
            "reason": str(reason),
            "scope": scope_text,
            "token_scope": token_scope_text,
            "detail": str(detail),
        },
    )
    json_part = f"json={json_field} " if machine_json_enabled() else ""
    print(
        f"HONGZHI_INDEX_BLOCK code={int(code)} reason={reason} command={command} "
        f"scope={scope_text} "
        f"token_scope={token_scope_text} "
        f"{json_part}"
        f"company_scope={quote_machine_value(company_scope_runtime())} "
        f"package_version={versions['package_version']} "
        f"plugin_version={versions['plugin_version']} "
        f"contract_version={versions['contract_version']} "
        f"detail={quote_machine_value(detail)}"
    )


def federated_index_policy_enabled(governance: dict) -> bool:
    return bool(governance.get("federated_index_enabled", governance.get("enabled", False)))


def federated_index_scope_allowed(governance: dict) -> Tuple[bool, str]:
    if not isinstance(governance, dict):
        return False, "governance_missing"
    if not governance.get("token_used", False):
        return True, "allowed"
    scope = normalize_scope(governance.get("token_scope"))
    if "*" in scope or "federated_index" in scope:
        return True, "allowed"
    return False, "token_scope_missing"


def metrics_bool(value: Any) -> bool:
    return bool(value)


def run_layout_adapters(
    repo_root: Path,
    candidates: List[dict],
    keywords: List[str],
    hint_identity: dict,
    fallback_layout: str,
) -> dict:
    try:
        import layout_adapters as la  # local script in prompt-dsl-system/tools

        result = la.analyze_layout(
            repo_root=repo_root,
            candidates=candidates,
            keywords=keywords,
            hint_identity=hint_identity,
            fallback_layout=fallback_layout,
        )
        if isinstance(result, dict):
            return result
    except Exception as exc:
        print(f"[plugin] WARN: layout_adapters failed: {exc}", file=sys.stderr)

    return {
        "layout": fallback_layout or "unknown",
        "roots_entries": [],
        "java_roots": [],
        "template_roots": [],
        "layout_details": {
            "adapter_used": "layout_adapters_fallback",
            "candidates_scanned": len(candidates or []),
            "java_roots_detected": 0,
            "template_roots_detected": 0,
            "keywords_used": len(keywords or []),
            "hint_identity_present": bool(hint_identity),
            "fallback_reason": "adapter_import_or_runtime_failure",
        },
    }


def build_roots_entries_from_detected_roots(
    repo_root: Path,
    candidates: List[dict],
    java_roots: List[Path],
    template_roots: List[Path],
) -> List[dict]:
    """Build roots entries using already-detected roots (avoid repeated full layout scan)."""
    try:
        import layout_adapters as la

        if hasattr(la, "build_roots_entries"):
            return la.build_roots_entries(
                repo_root=repo_root,
                candidates=candidates,
                java_roots=[str(p) for p in java_roots],
                template_roots=[str(p) for p in template_roots],
            )
    except Exception:
        pass

    entries: List[dict] = []
    for cand in candidates or []:
        if not isinstance(cand, dict):
            continue
        module_key = str(cand.get("module_key", "") or "")
        package_prefix = str(cand.get("package_prefix", "") or "")
        backend = []
        template = []
        pkg_path = package_prefix.replace(".", "/")
        for root in java_roots:
            if not root.is_dir():
                continue
            target = root / pkg_path if pkg_path else root
            backend.append(normalize_rel(str(target), repo_root))
        for root in template_roots:
            if not root.is_dir():
                continue
            template.append(normalize_rel(str(root), repo_root))
        roots = [{"kind": "backend_java", "path": p} for p in backend if p] + [
            {"kind": "web_template", "path": p} for p in template if p
        ]
        entries.append({"module_key": module_key, "package_prefix": package_prefix, "roots": roots})
    return entries


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


def detect_vcs_info(repo_root: Path) -> Dict[str, str]:
    vcs = {"kind": "none", "head": "none"}
    if not (repo_root / ".git").exists():
        return vcs
    vcs["kind"] = "git"
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            vcs["head"] = proc.stdout.strip()
            return vcs
    except Exception:
        pass

    # Fallback to .git/HEAD text if git command is unavailable.
    head_path = repo_root / ".git" / "HEAD"
    if head_path.exists():
        try:
            vcs["head"] = head_path.read_text(encoding="utf-8").strip() or "unknown"
        except OSError:
            vcs["head"] = "unknown"
    return vcs


def compute_cache_hit_rate(cache_hit: int, cache_miss: int) -> float:
    total = cache_hit + cache_miss
    if total <= 0:
        return 0.0
    return round(cache_hit / total, 4)


def normalize_rel(path_value: str, parent_dir: Path) -> str:
    try:
        return str(Path(path_value).resolve().relative_to(parent_dir.resolve()))
    except Exception:
        return str(path_value)


def link_or_copy_path(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        if src.is_dir():
            os.symlink(str(src), str(dst), target_is_directory=True)
        else:
            os.symlink(str(src), str(dst))
    except OSError:
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


def expected_reuse_artifacts_exist(workspace: Path, command: str) -> bool:
    if command == "discover":
        discover_dir = workspace / "discover"
        if not (discover_dir / "auto_discover.yaml").is_file():
            return False
        has_structure = any(discover_dir.glob("*.structure.yaml"))
        return has_structure or (workspace / "capabilities.json").is_file()
    if command == "profile":
        return any((workspace / "profile").glob("*.profile.yaml"))
    if command == "diff":
        return any((workspace / "diff").glob("*.diff.yaml"))
    if command == "migrate":
        return (workspace / "migrate" / "migrate_intent.json").is_file()
    return False


def collect_command_artifacts(workspace: Path, command: str) -> List[str]:
    command_dir = workspace / command
    if not command_dir.exists():
        return []
    artifacts = []
    for fp in command_dir.rglob("*"):
        if fp.is_file():
            artifacts.append(str(fp))
    artifacts.sort()
    return artifacts


def load_workspace_capabilities(workspace: Path) -> dict:
    cap_file = workspace / "capabilities.json"
    if not cap_file.is_file():
        return {}
    try:
        loaded = json.loads(cap_file.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            return loaded
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def resolve_scan_graph_roots(
    repo_root: Path,
    java_roots: List[Path],
    template_roots: List[Path],
) -> List[str]:
    roots: List[str] = []
    seen = set()
    for p in (java_roots or []) + (template_roots or []):
        if not isinstance(p, Path):
            continue
        if not p.is_dir():
            continue
        try:
            rel = str(p.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
            if rel and rel not in seen:
                seen.add(rel)
                roots.append(rel)
        except ValueError:
            continue
    return roots


def build_discover_scan_graph(
    *,
    repo_root: Path,
    workspace: Path,
    roots: List[str],
    keywords: List[str],
    max_files: Optional[int],
    max_seconds: Optional[int],
    producer_versions: Optional[dict] = None,
) -> Tuple[dict, Path]:
    cache_dir = workspace / "scan_cache"
    payload = build_scan_graph(
        repo_root=repo_root,
        roots=roots,
        max_files=max_files,
        max_seconds=max_seconds,
        keywords=keywords,
        cache_dir=cache_dir,
        producer_versions=producer_versions,
    )
    out_path = workspace / "discover" / "scan_graph.json"
    save_scan_graph(out_path, payload)
    return payload, out_path


def load_scan_graph_any(path_value: str | Path) -> dict:
    try:
        return load_scan_graph(Path(path_value).expanduser().resolve())
    except Exception:
        return {}


def scan_graph_to_structure_inputs(payload: dict) -> Tuple[List[dict], List[str], dict]:
    file_index = payload.get("file_index", {}) if isinstance(payload.get("file_index"), dict) else {}
    java_hints = payload.get("java_hints", []) if isinstance(payload.get("java_hints"), list) else []
    template_items = file_index.get("templates", []) if isinstance(file_index.get("templates"), list) else []

    java_results: List[dict] = []
    for hint in java_hints:
        if not isinstance(hint, dict):
            continue
        java_results.append(
            {
                "rel_path": str(hint.get("rel_path", "") or ""),
                "package": str(hint.get("package", "") or ""),
                "is_controller": bool(hint.get("is_controller", False)),
                "is_service": bool(hint.get("is_service", False)),
                "is_repository": bool(hint.get("is_repository", False)),
                "is_entity": bool(hint.get("is_entity", False)),
                "is_dto": bool(hint.get("is_dto", False)),
                "endpoints": hint.get("endpoints", []) if isinstance(hint.get("endpoints", []), list) else [],
                "endpoint_signatures": hint.get("endpoint_signatures", []) if isinstance(hint.get("endpoint_signatures", []), list) else [],
                "class_name": str(hint.get("class_name", "") or ""),
                "parse_uncertain": bool(hint.get("parse_uncertain", False)),
            }
        )

    templates: List[str] = []
    for item in template_items:
        if isinstance(item, dict):
            rel = str(item.get("relpath", "") or "")
            if rel:
                templates.append(rel)
        elif isinstance(item, str):
            templates.append(item)

    io_stats = payload.get("io_stats", {}) if isinstance(payload.get("io_stats"), dict) else {}
    return java_results, sorted(set(templates)), io_stats


def scan_graph_spot_check(repo_root: Path, java_results: List[dict], sample_size: int = 8) -> dict:
    """
    Spot-check scan_graph Java hints against full parser on a deterministic sample.
    """
    if not java_results:
        return {"sampled": 0, "mismatches": 0, "ratio": 0.0, "details": []}

    try:
        import structure_discover as sd  # local script import
    except Exception:
        return {"sampled": 0, "mismatches": 0, "ratio": 0.0, "details": []}

    sample = sorted(
        [r for r in java_results if isinstance(r, dict) and r.get("rel_path")],
        key=lambda x: str(x.get("rel_path", "")),
    )[: max(1, int(sample_size))]
    mismatches = 0
    details: List[str] = []
    for item in sample:
        rel = str(item.get("rel_path", ""))
        fp = repo_root / rel
        if not fp.is_file():
            continue
        try:
            full = sd.scan_java_file(fp, repo_root)
        except Exception:
            continue
        checks = [
            ("controller", bool(item.get("is_controller", False)), bool(full.get("is_controller", False))),
            ("service", bool(item.get("is_service", False)), bool(full.get("is_service", False))),
            ("repository", bool(item.get("is_repository", False)), bool(full.get("is_repository", False))),
        ]
        lite_ep = len(item.get("endpoint_signatures", []) if isinstance(item.get("endpoint_signatures", []), list) else [])
        full_ep = len(full.get("endpoint_signatures", []) if isinstance(full.get("endpoint_signatures", []), list) else [])
        mismatch_here = False
        for tag, lval, fval in checks:
            if lval != fval:
                mismatch_here = True
                details.append(f"{rel}:{tag}:{int(lval)}!={int(fval)}")
        if lite_ep != full_ep:
            mismatch_here = True
            details.append(f"{rel}:endpoint_count:{lite_ep}!={full_ep}")
        if mismatch_here:
            mismatches += 1

    sampled = len(sample)
    ratio = float(mismatches) / float(sampled) if sampled > 0 else 0.0
    return {"sampled": sampled, "mismatches": mismatches, "ratio": round(ratio, 4), "details": details[:12]}


def find_latest_scan_graph_by_fp(
    global_state_root: Path,
    fp: str,
    workspace_root_hint: Optional[Path] = None,
) -> str:
    latest_path = global_state_root / fp / "latest.json"
    latest_workspace = ""
    if latest_path.is_file():
        try:
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            latest = {}
        if isinstance(latest, dict):
            latest_workspace = str(latest.get("workspace", "") or "")

    if latest_workspace:
        candidate = Path(latest_workspace).expanduser().resolve() / "discover" / "scan_graph.json"
        if candidate.is_file():
            return str(candidate)

    search_roots: List[Path] = []
    if latest_workspace:
        ws_path = Path(latest_workspace).expanduser().resolve()
        if ws_path.parent.name == fp:
            search_roots.append(ws_path.parent)
        elif ws_path.name == fp:
            search_roots.append(ws_path)
    if isinstance(workspace_root_hint, Path):
        hinted = workspace_root_hint.expanduser().resolve() / fp
        if hinted not in search_roots:
            search_roots.append(hinted)
    try:
        default_ws = resolve_workspace_root(read_only=True) / fp
        if default_ws not in search_roots:
            search_roots.append(default_ws)
    except Exception:
        pass

    latest_graph = ""
    latest_mtime = -1
    for root in search_roots:
        if not root.exists():
            continue
        for candidate in root.rglob("discover/scan_graph.json"):
            if not candidate.is_file():
                continue
            try:
                st = candidate.stat()
            except OSError:
                continue
            if st.st_mtime_ns > latest_mtime:
                latest_mtime = st.st_mtime_ns
                latest_graph = str(candidate.resolve())
    return latest_graph


def classes_from_scan_graph(payload: dict, module_key: str) -> dict:
    classes: dict = {}
    hints = payload.get("java_hints", []) if isinstance(payload.get("java_hints"), list) else []
    module_key_l = str(module_key or "").lower()
    for hint in hints:
        if not isinstance(hint, dict):
            continue
        pkg = str(hint.get("package", "") or "")
        rel = str(hint.get("rel_path", "") or "")
        cls_name = str(hint.get("class_name", "") or "") or Path(rel).stem
        if module_key_l and module_key_l not in pkg.lower() and module_key_l not in cls_name.lower() and module_key_l not in rel.lower():
            continue
        key = cls_name
        if key in classes:
            key = f"{cls_name}@{rel}"
        classes[key] = {
            "file": rel,
            "package": pkg,
            "endpoint_signatures": hint.get("endpoint_signatures", []) if isinstance(hint.get("endpoint_signatures", []), list) else [],
        }
    return classes


def templates_from_scan_graph(payload: dict, module_key: str) -> set:
    file_index = payload.get("file_index", {}) if isinstance(payload.get("file_index"), dict) else {}
    entries = file_index.get("templates", []) if isinstance(file_index.get("templates"), list) else []
    module_key_l = str(module_key or "").lower()
    out = set()
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
        out.add(Path(rel).name)
    return out


def write_profile_from_scan_graph(profile_path: Path, module_key: str, scan_graph_payload: dict) -> None:
    file_index = scan_graph_payload.get("file_index", {}) if isinstance(scan_graph_payload.get("file_index"), dict) else {}
    io_stats = scan_graph_payload.get("io_stats", {}) if isinstance(scan_graph_payload.get("io_stats"), dict) else {}
    lines = [
        "# Auto-generated by hongzhi_plugin profile --scan-graph",
        f'module_key: "{module_key}"',
        f'generated_at: "{utc_now_iso()}"',
        "source:",
        f'  kind: "scan_graph"',
        f'  cache_key: "{scan_graph_payload.get("cache_key", "")}"',
        f'  cache_source: "{scan_graph_payload.get("cache_source", "")}"',
        "scan_io_stats:",
        f'  files_indexed: {int(io_stats.get("files_indexed", 0) or 0)}',
        f'  java_scanned: {int(io_stats.get("java_scanned", 0) or 0)}',
        f'  template_scanned: {int(io_stats.get("template_scanned", 0) or 0)}',
        f'  bytes_read: {int(io_stats.get("bytes_read", 0) or 0)}',
        "",
        "file_index_counts:",
    ]
    for key in ("java", "templates", "resources", "other"):
        values = file_index.get(key, []) if isinstance(file_index.get(key), list) else []
        lines.append(f"  {key}: {len(values)}")
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def summarize_governance(gov_info: dict) -> str:
    return "enabled" if gov_info.get("enabled") else "disabled"


def ensure_endpoints_total(metrics: dict) -> int:
    if "endpoints_total" in metrics:
        try:
            return int(metrics["endpoints_total"])
        except (TypeError, ValueError):
            pass
    total = 0
    for key, value in metrics.items():
        if key.startswith("endpoints_"):
            try:
                total += int(value)
            except (TypeError, ValueError):
                continue
    metrics["endpoints_total"] = total
    return total


def is_subpath(candidate: Path, parent: Path) -> bool:
    try:
        candidate.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def assert_output_roots_safe(repo_root: Path, workspace: Path, global_state_root: Path) -> None:
    if is_subpath(workspace, repo_root):
        print(
            f"FAIL: workspace path must not be under repo_root ({workspace} under {repo_root})",
            file=sys.stderr,
        )
        sys.exit(1)
    if is_subpath(global_state_root, repo_root):
        print(
            f"FAIL: global_state_root must not be under repo_root ({global_state_root} under {repo_root})",
            file=sys.stderr,
        )
        sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
#  Governance Logic
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_bool_literal(value: str) -> bool:
    val = str(value).strip().lower()
    if val == "true":
        return True
    if val == "false":
        return False
    raise ValueError(f"invalid bool literal: {value}")


def _parse_inline_list(value: str) -> List[str]:
    text = str(value).strip()
    if not (text.startswith("[") and text.endswith("]")):
        raise ValueError("expected inline list syntax")
    inner = text[1:-1].strip()
    if not inner:
        return []
    return [x.strip().strip("\"'") for x in inner.split(",") if x.strip()]


def load_policy_yaml(args_dict):
    """Load governance policy from policy.yaml (simple parser, fail-closed)."""
    kit_root = None
    if args_dict.get("kit_root"):
        kit_root = Path(args_dict["kit_root"])
    else:
        try:
            kit_root = SCRIPT_DIR.parent.parent
        except Exception:
            pass

    policy = {
        "enabled": False,
        "allow_roots": [],
        "deny_roots": [],
        "permit_token_file": None,
        "federated_index": {
            "enabled": None,  # None => inherit plugin.enabled
            "write_jsonl": True,
            "write_repo_mirror": True,
        },
        "_parse_error": False,
        "_parse_error_reason": "",
    }

    if os.environ.get(GOVERNANCE_ENV) == "1":
        policy["enabled"] = True

    if not kit_root:
        return policy

    policy_path = kit_root / "policy.yaml"
    if not policy_path.exists():
        return policy

    def fail_parse(reason: str) -> dict:
        policy["_parse_error"] = True
        policy["_parse_error_reason"] = f"{policy_path}: {reason}"
        return policy

    try:
        content = policy_path.read_text(encoding="utf-8")
    except OSError as exc:
        return fail_parse(f"read_failed: {exc}")

    in_plugin = False
    in_federated = False
    plugin_indent = 0
    federated_indent = 0
    pending_list = None
    pending_list_indent = 0

    for lineno, raw_line in enumerate(content.splitlines(), 1):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))

        if pending_list:
            if indent > pending_list_indent and stripped.startswith("-"):
                item = stripped[1:].strip().strip("\"'")
                if item:
                    policy[pending_list].append(str(canonical_path(item)))
                continue
            pending_list = None

        if stripped == "plugin:":
            in_plugin = True
            in_federated = False
            plugin_indent = indent
            continue

        if not in_plugin:
            # Allow unrelated top-level sections.
            continue

        if indent <= plugin_indent:
            in_plugin = False
            in_federated = False
            if stripped == "plugin:":
                in_plugin = True
                plugin_indent = indent
                continue
            continue

        if stripped == "federated_index:":
            in_federated = True
            federated_indent = indent
            continue

        if in_federated and indent <= federated_indent:
            in_federated = False

        if ":" not in stripped:
            return fail_parse(f"line {lineno}: malformed yaml entry")

        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()

        if in_federated:
            if key not in ("enabled", "write_jsonl", "write_repo_mirror"):
                return fail_parse(f"line {lineno}: unsupported federated_index key '{key}'")
            if not raw_value:
                return fail_parse(f"line {lineno}: empty value for federated_index.{key}")
            try:
                policy["federated_index"][key] = _parse_bool_literal(raw_value)
            except ValueError as exc:
                return fail_parse(f"line {lineno}: {exc}")
            continue

        if key == "enabled":
            try:
                policy["enabled"] = _parse_bool_literal(raw_value)
            except ValueError as exc:
                return fail_parse(f"line {lineno}: {exc}")
            continue

        if key in ("allow_roots", "deny_roots"):
            if not raw_value:
                policy[key] = []
                pending_list = key
                pending_list_indent = indent
                continue
            try:
                parsed = _parse_inline_list(raw_value)
            except ValueError:
                return fail_parse(f"line {lineno}: {key} requires inline list or block list")
            policy[key] = [str(canonical_path(item)) for item in parsed if str(item).strip()]
            continue

        if key == "permit_token_file":
            if not raw_value:
                policy["permit_token_file"] = None
            else:
                policy["permit_token_file"] = raw_value.strip("\"'")
            continue

        if key == "federated_index":
            return fail_parse(f"line {lineno}: federated_index must be a nested object block")

        return fail_parse(f"line {lineno}: unsupported plugin key '{key}'")

    return policy

def check_root_governance(policy, repo_root, command, permit_token=None):
    """
    Check if repo_root is allowed.
    Returns: (allowed: bool, exit_code: int, reason: str, token_used: bool, token_info: dict)
    Priorities:
      1. Permit Token (if valid + unexpired + scope match) -> ALLOW
      2. Deny List -> BLOCK (11)
      3. Allow List (if not empty) -> BLOCK (12) if not present
      4. Default -> ALLOW
    """
    repo_path = canonical_path(repo_root)

    # Check permit token override
    token_used = False
    effective_token = permit_token
    if not effective_token and policy.get("permit_token_file"):
        tok_path = Path(policy["permit_token_file"]).expanduser()
        if tok_path.exists():
            try:
                effective_token = tok_path.read_text(encoding="utf-8").strip()
            except OSError:
                pass

    token_info = parse_permit_token(effective_token)
    if token_info.get("provided"):
        token_ok, token_reason = validate_permit_token(token_info, command)
        token_info["validated_reason"] = token_reason
        if token_ok:
            # Token present — bypass allow/deny (but NOT read-only contract)
            token_used = True
            return True, 0, "permit-token override", True, token_info
        return (
            False,
            GOVERNANCE_ALLOW_EXIT_CODE,
            f"permit-token rejected: {token_reason}",
            False,
            token_info,
        )

    # Check Deny List
    for denied in policy["deny_roots"]:
        if is_path_within(repo_path, denied):
            return (
                False,
                GOVERNANCE_DENY_EXIT_CODE,
                f"repo path denied by policy: {canonical_path(denied)}",
                False,
                token_info,
            )

    # Check Allow List
    if policy["allow_roots"]:
        allowed_found = False
        for allowed in policy["allow_roots"]:
            if is_path_within(repo_path, allowed):
                allowed_found = True
                break
        if not allowed_found:
            return (
                False,
                GOVERNANCE_ALLOW_EXIT_CODE,
                "repo path not in allow_roots",
                False,
                token_info,
            )
    
    # No allow_roots defined or matched -> allow
    return True, 0, "allowed by policy", False, token_info

def check_governance_full(args):
    """Full governance check including enabled status and root validation."""
    args_dict = vars(args)
    policy = load_policy_yaml(args_dict)

    fed_policy = policy.get("federated_index", {}) if isinstance(policy.get("federated_index"), dict) else {}
    fed_enabled_raw = fed_policy.get("enabled", None)
    if fed_enabled_raw is None:
        fed_enabled = bool(policy["enabled"])
    else:
        fed_enabled = bool(fed_enabled_raw)
    gov_info = {
        "enabled": policy["enabled"],
        "token_used": False,
        "policy_loaded": not bool(policy.get("_parse_error", False)),
        "policy_hash": compute_policy_hash(policy),
        "token_reason": "token_not_provided",
        "token_scope": ["*"],
        "policy_parse_error": bool(policy.get("_parse_error", False)),
        "company_scope": company_scope_runtime(),
        "company_scope_required": bool(company_scope_required_runtime()),
        "federated_index_enabled": fed_enabled,
        "federated_index_write_jsonl": bool(fed_policy.get("write_jsonl", True)),
        "federated_index_write_repo_mirror": bool(fed_policy.get("write_repo_mirror", True)),
    }

    if policy.get("_parse_error"):
        return (
            False,
            POLICY_PARSE_EXIT_CODE,
            str(policy.get("_parse_error_reason", "policy_parse_error")),
            gov_info,
        )

    if not policy["enabled"]:
        return False, GOVERNANCE_EXIT_CODE, "plugin runner disabled", gov_info

    # If repo-root is involved, check it (including diff old/new roots).
    repo_targets: List[Path] = []
    if args_dict.get("repo_root"):
        repo_targets.append(Path(args_dict["repo_root"]).resolve())
    elif args_dict.get("new_project_root"):
        repo_targets.append(Path(args_dict["new_project_root"]).resolve())
        if args_dict.get("old_project_root"):
            repo_targets.append(Path(args_dict["old_project_root"]).resolve())

    permit_token = args_dict.get("permit_token")
    for target_repo in repo_targets:
        allowed, code, reason, token_used, token_info = check_root_governance(
            policy, target_repo, args.command, permit_token
        )
        gov_info["token_used"] = bool(gov_info["token_used"] or token_used)
        gov_info["token_reason"] = token_info.get("validated_reason", token_info.get("reason", "token_not_provided"))
        gov_info["token_scope"] = token_info.get("scope", ["*"])
        if not allowed:
             return False, code, f"{target_repo}: {reason}", gov_info

    return True, 0, "allowed", gov_info


# ═══════════════════════════════════════════════════════════════════════════════
#  Workspace resolution
# ═══════════════════════════════════════════════════════════════════════════════

def compute_project_fingerprint(repo_root):
    """Stable 12-char hash of repo identity (path + HEAD + top-level file count)."""
    parts = [str(repo_root.resolve())]
    vcs = detect_vcs_info(repo_root)
    parts.append(vcs.get("kind", "none"))
    parts.append(vcs.get("head", "none"))
    # Top-level file count (cheap)
    try:
        top_count = sum(1 for _ in repo_root.iterdir() if _.is_file())
    except OSError:
        top_count = 0
    parts.append(str(top_count))
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:12]


def resolve_workspace(fingerprint, run_id, override_root=None, read_only: bool = False):
    """Resolve workspace directory with fallback chain."""
    try:
        workspace_root = resolve_workspace_root(override_root, read_only=read_only)
        ws = workspace_root / fingerprint / run_id
        if not read_only:
            ws.mkdir(parents=True, exist_ok=True)
        return ws
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
#  Snapshot-based read-only contract
# ═══════════════════════════════════════════════════════════════════════════════

def take_snapshot(repo_root, max_files=None):
    """Lightweight snapshot: {relpath: (size, mtime_ns)} for files under repo_root."""
    snap = {}
    count = 0
    for root, dirs, files in os.walk(str(repo_root)):
        dirs[:] = [d for d in dirs if d not in SNAPSHOT_EXCLUDES]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in SNAPSHOT_EXT_EXCLUDES:
                continue
            fp = os.path.join(root, f)
            try:
                st = os.stat(fp)
                rel = os.path.relpath(fp, str(repo_root))
                snap[rel] = (st.st_size, st.st_mtime_ns)
            except OSError:
                pass
            count += 1
            if max_files and count >= max_files:
                return snap  # early stop
    return snap


def diff_snapshots(before, after):
    """Compare two snapshots, return dict of created/deleted/modified files."""
    created = []
    deleted = []
    modified = []
    for rel in after:
        if rel not in before:
            created.append(rel)
        elif after[rel] != before[rel]:
            modified.append(rel)
    for rel in before:
        if rel not in after:
            deleted.append(rel)
    return {"created": created, "deleted": deleted, "modified": modified}


def enforce_read_only(delta, write_ok):
    """If write_ok is False and delta is non-empty, FAIL with exit code 3."""
    total = len(delta["created"]) + len(delta["deleted"]) + len(delta["modified"])
    if total == 0:
        return True
    if write_ok:
        print(f"[plugin] NOTE: {total} file(s) changed in project repo (--write-ok active)",
              file=sys.stderr)
        return True
    print(f"[plugin] FAIL: read-only contract violated — {total} file(s) changed in project repo:",
          file=sys.stderr)
    for cat in ("created", "deleted", "modified"):
        for f in delta[cat][:5]:
            print(f"  [{cat}] {f}", file=sys.stderr)
    sys.exit(3)


# ═══════════════════════════════════════════════════════════════════════════════
#  Capabilities output
# ═══════════════════════════════════════════════════════════════════════════════

def sort_artifacts_stable(artifacts: List[Any], workspace: Path) -> List[Any]:
    def key_for(item: Any) -> tuple:
        text = str(item)
        try:
            p = Path(text).expanduser().resolve()
            if is_path_within(p, workspace):
                rel = str(p.relative_to(workspace)).replace("\\", "/")
                return (0, rel)
            if is_path_within(p, workspace.parent):
                rel = str(p.relative_to(workspace.parent)).replace("\\", "/")
                return (1, rel)
            return (2, str(p))
        except Exception:
            return (3, text)
    return sorted(list(artifacts or []), key=key_for)


def sort_roots_stable(roots: List[Any]) -> List[Any]:
    normalized: List[dict] = []
    for item in roots or []:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        nested_roots = entry.get("roots", [])
        if isinstance(nested_roots, list):
            sorted_nested = []
            for root_item in nested_roots:
                if isinstance(root_item, dict):
                    sorted_nested.append(dict(root_item))
            sorted_nested.sort(
                key=lambda r: (
                    str(r.get("category", "")),
                    str(r.get("kind", "")),
                    str(r.get("path", "")),
                )
            )
            entry["roots"] = sorted_nested
        normalized.append(entry)
    normalized.sort(
        key=lambda e: (
            str(e.get("module_key", "")),
            str(e.get("category", "")),
            str(e.get("path", "")),
            str(e.get("package_prefix", "")),
        )
    )
    return normalized


def sort_candidates_stable(candidates: List[Any]) -> List[Any]:
    normalized: List[dict] = []
    for item in candidates or []:
        if isinstance(item, dict):
            normalized.append(dict(item))
    normalized.sort(
        key=lambda c: (
            -float(c.get("score", 0.0) or 0.0),
            str(c.get("module_key", "")),
            str(c.get("package_prefix", "")),
            str(c.get("path", "")),
        )
    )
    return normalized


def write_capabilities(
    workspace,
    command,
    run_id,
    repo_fingerprint,
    layout,
    roots,
    artifacts,
    metrics,
    warnings,
    suggestions,
    governance=None,
    smart=None,
    capability_registry=None,
    calibration=None,
    hints=None,
    hint_bundle=None,
    layout_details=None,
    federated_index=None,
):
    """Write capabilities.json for agent-detectable output (contract v4, backward compatible)."""
    versions = version_triplet()
    scan_stats = build_scan_stats(metrics)
    limits = metrics.get("limits", {"max_files": None, "max_seconds": None})
    if not isinstance(limits, dict):
        limits = {"max_files": None, "max_seconds": None}
    calibration_payload = calibration if isinstance(calibration, dict) else {}
    calibration_payload = {
        "needs_human_hint": bool(calibration_payload.get("needs_human_hint", False)),
        "confidence": float(calibration_payload.get("confidence", 1.0) or 0.0),
        "confidence_tier": str(calibration_payload.get("confidence_tier", "high")),
        "reasons": calibration_payload.get("reasons", []) if isinstance(calibration_payload.get("reasons", []), list) else [],
        "suggested_hints_path": str(calibration_payload.get("suggested_hints_path", "")),
        "report_path": str(calibration_payload.get("report_path", "")),
        "report_json_path": str(calibration_payload.get("report_json_path", "")),
        "suggested_hints": calibration_payload.get("suggested_hints", {}) if isinstance(calibration_payload.get("suggested_hints", {}), dict) else {},
        "action_suggestions": calibration_payload.get("action_suggestions", []) if isinstance(calibration_payload.get("action_suggestions", []), list) else [],
        "metrics_snapshot": calibration_payload.get("metrics_snapshot", {}) if isinstance(calibration_payload.get("metrics_snapshot", {}), dict) else {},
    }
    hints_payload = hints if isinstance(hints, dict) else {}
    hints_payload = {
        "emitted": bool(hints_payload.get("emitted", False)),
        "applied": bool(hints_payload.get("applied", False)),
        "bundle_path": str(hints_payload.get("bundle_path", "")),
        "source_path": str(hints_payload.get("source_path", "")),
        "strategy": str(hints_payload.get("strategy", "conservative")),
        "hint_effective": bool(hints_payload.get("effective", False)),
        "confidence_delta": float(hints_payload.get("confidence_delta", 0.0) or 0.0),
    }
    layout_details_payload = layout_details if isinstance(layout_details, dict) else {}
    hint_bundle_payload = hint_bundle if isinstance(hint_bundle, dict) else {}
    hint_bundle_payload = {
        "kind": str(hint_bundle_payload.get("kind", "") or ""),
        "path": str(hint_bundle_payload.get("path", "") or ""),
        "verified": bool(hint_bundle_payload.get("verified", False)),
        "expired": bool(hint_bundle_payload.get("expired", False)),
        "ttl_seconds": int(hint_bundle_payload.get("ttl_seconds", 0) or 0),
        "created_at": str(hint_bundle_payload.get("created_at", "") or ""),
        "expires_at": str(hint_bundle_payload.get("expires_at", "") or ""),
    }
    metrics_payload = dict(metrics) if isinstance(metrics, dict) else {}
    if isinstance(metrics_payload.get("candidates"), list):
        metrics_payload["candidates"] = sort_candidates_stable(metrics_payload.get("candidates", []))
    if isinstance(metrics_payload.get("module_candidates_list"), list):
        metrics_payload["module_candidates_list"] = sort_candidates_stable(metrics_payload.get("module_candidates_list", []))

    caps = {
        "version": PLUGIN_VERSION,
        "package_version": versions["package_version"],
        "plugin_version": versions["plugin_version"],
        "contract_version": versions["contract_version"],
        "summary_version": SUMMARY_VERSION,
        "company_scope": company_scope_runtime(),
        "command": command,
        "run_id": run_id,
        "repo_fingerprint": repo_fingerprint,
        "timestamp": utc_now_iso(),
        "layout": layout,
        "module_candidates": as_int(metrics.get("module_candidates", len(roots)), len(roots)),
        "ambiguity_ratio": float(metrics.get("ambiguity_ratio", 0.0) or 0.0),
        "limits_hit": bool(metrics.get("limits_hit", False)),
        "limits_suggestion": str(metrics.get("limits_suggestion", "")),
        "limits": {
            "max_files": limits.get("max_files"),
            "max_seconds": limits.get("max_seconds"),
            "reason": metrics.get("limits_reason", ""),
            "reason_code": metrics.get("limits_reason_code", "-"),
        },
        "scan_stats": scan_stats,
        "scan_io_stats": metrics.get("scan_io_stats", {}) if isinstance(metrics.get("scan_io_stats"), dict) else {},
        "scan_graph": metrics.get("scan_graph", {}) if isinstance(metrics.get("scan_graph"), dict) else {},
        "layout_details": layout_details_payload,
        "hints": hints_payload,
        "hint_bundle": hint_bundle_payload,
        "calibration": calibration_payload,
        "roots": sort_roots_stable(roots if isinstance(roots, list) else []),
        "artifacts": sort_artifacts_stable(artifacts if isinstance(artifacts, list) else [], Path(workspace)),
        "metrics": metrics_payload,
        "warnings": warnings,
        "suggestions": suggestions,
        "governance": governance or {},
        "smart": smart or {
            "enabled": False,
            "reused": False,
            "reused_from_run_id": None,
            "reuse_validated": False,
        },
        "capability_registry": capability_registry or {},
        "federated_index": federated_index or {},
        "stdout_contract": {
            "v3_summary_prefix": "hongzhi_ai_kit_summary",
            "v4_caps_prefix": "HONGZHI_CAPS",
            "v4_status_prefix": "HONGZHI_STATUS",
            "v4_governance_block_prefix": "HONGZHI_GOV_BLOCK",
        },
        "workspace_journal": {
            "capabilities_jsonl": str((workspace.parent / "capabilities.jsonl").resolve()),
        },
    }
    cap_path = workspace / "capabilities.json"
    atomic_write_json(cap_path, caps)
    return cap_path


def print_summary_line(command, fp, run_id, smart_info, metrics, governance):
    """Print single-line agent-detectable summary (fixed key contract)."""
    versions = version_triplet()
    modules = metrics.get("module_candidates", metrics.get("modules", 0))
    endpoints = metrics.get("endpoints_total", 0)
    scan_time = metrics.get("scan_time_s", 0)
    reused = 1 if smart_info.get("reused") else 0
    reuse_validated = 1 if smart_info.get("reuse_validated") else 0
    reused_from = smart_info.get("reused_from_run_id") or "-"
    gov_state = summarize_governance(governance)
    limits_hit = 1 if metrics.get("limits_hit") else 0
    limits_reason_code = metrics.get("limits_reason_code", "-")
    needs_human_hint = 1 if metrics.get("needs_human_hint") else 0
    confidence_tier = metrics.get("confidence_tier", "-")
    ambiguity_ratio = float(metrics.get("ambiguity_ratio", 0.0) or 0.0)
    exit_hint = str(metrics.get("exit_hint", "-") or "-")
    hint_applied = 1 if metrics.get("hint_applied") else 0
    hint_bundle = str(metrics.get("hint_bundle", "-") or "-")
    hint_bundle_kind = str(metrics.get("hint_bundle_kind", "-") or "-")
    hint_verified = 1 if metrics.get("hint_verified") else 0
    hint_expired = 1 if metrics.get("hint_expired") else 0
    hint_effective = 1 if metrics.get("hint_effective") else 0
    confidence_delta = float(metrics.get("confidence_delta", 0.0) or 0.0)
    mismatch_reason = str(metrics.get("mismatch_reason", "-") or "-")
    mismatch_detail = str(metrics.get("mismatch_detail", "-") or "-").replace(" ", "_")
    mismatch_suggestion = str(metrics.get("mismatch_suggestion", "-") or "-").replace(" ", "_")
    scan_graph_payload = metrics.get("scan_graph", {}) if isinstance(metrics.get("scan_graph"), dict) else {}
    scan_graph_used = 1 if scan_graph_payload.get("used") else 0
    scan_cache_hit_rate = float(
        scan_graph_payload.get(
            "cache_hit_rate",
            scan_graph_payload.get("io_stats", {}).get("cache_hit_rate", 0.0)
            if isinstance(scan_graph_payload.get("io_stats"), dict)
            else 0.0,
        )
        or 0.0
    )
    java_files_indexed = int(
        scan_graph_payload.get(
            "java_files_indexed",
            scan_graph_payload.get("io_stats", {}).get("java_scanned", 0)
            if isinstance(scan_graph_payload.get("io_stats"), dict)
            else 0,
        )
        or 0
    )
    scan_bytes_read = int(
        scan_graph_payload.get(
            "bytes_read",
            scan_graph_payload.get("io_stats", {}).get("bytes_read", 0)
            if isinstance(scan_graph_payload.get("io_stats"), dict)
            else 0,
        )
        or 0
    )
    print(
        "hongzhi_ai_kit_summary "
        f"version={SUMMARY_VERSION} "
        f"package_version={versions['package_version']} "
        f"plugin_version={versions['plugin_version']} "
        f"contract_version={versions['contract_version']} "
        f"company_scope={company_scope_runtime().replace(' ', '_')} "
        f"command={command} "
        f"fp={fp} "
        f"run_id={run_id} "
        f"smart_reused={reused} "
        f"reuse_validated={reuse_validated} "
        f"reused_from={reused_from} "
        f"needs_human_hint={needs_human_hint} "
        f"confidence_tier={confidence_tier} "
        f"ambiguity_ratio={ambiguity_ratio:.4f} "
        f"hint_applied={hint_applied} "
        f"hint_bundle={hint_bundle} "
        f"hint_bundle_kind={hint_bundle_kind} "
        f"hint_verified={hint_verified} "
        f"hint_expired={hint_expired} "
        f"hint_effective={hint_effective} "
        f"confidence_delta={confidence_delta:.4f} "
        f"mismatch_reason={mismatch_reason} "
        f"mismatch_detail={mismatch_detail} "
        f"mismatch_suggestion={mismatch_suggestion} "
        f"exit_hint={exit_hint} "
        f"limits_hit={limits_hit} "
        f"limits_reason={limits_reason_code} "
        f"modules={modules} "
        f"endpoints={endpoints} "
        f"scan_time_s={scan_time} "
        f"scan_graph_used={scan_graph_used} "
        f"scan_cache_hit_rate={scan_cache_hit_rate:.4f} "
        f"java_files_indexed={java_files_indexed} "
        f"bytes_read={scan_bytes_read} "
        f"governance={gov_state}"
    )


def print_caps_pointer_line(
    cap_path: Path,
    *,
    command: str,
    repo_fingerprint: str,
    run_id: str,
    mismatch_reason: str = "-",
    mismatch_detail: str = "-",
    mismatch_suggestion: str = "-",
) -> None:
    """Contract v4 machine-readable pointer to capabilities.json."""
    versions = version_triplet()
    resolved = cap_path.resolve()
    json_field = machine_json_field(
        path_value=resolved,
        command=command,
        repo_fingerprint=repo_fingerprint,
        run_id=run_id,
        extra={
            "mismatch_reason": str(mismatch_reason or "-"),
            "mismatch_detail": str(mismatch_detail or "-"),
            "mismatch_suggestion": str(mismatch_suggestion or "-"),
        },
    )
    json_part = f"json={json_field} " if machine_json_enabled() else ""
    print(
        f"HONGZHI_CAPS {resolved} "
        f"path={quote_machine_value(str(resolved))} "
        f"{json_part}"
        f"mismatch_reason={str(mismatch_reason or '-')} "
        f"mismatch_detail={quote_machine_value(str(mismatch_detail or '-'))} "
        f"mismatch_suggestion={quote_machine_value(str(mismatch_suggestion or '-'))} "
        f"company_scope={quote_machine_value(company_scope_runtime())} "
        f"package_version={versions['package_version']} "
        f"plugin_version={versions['plugin_version']} "
        f"contract_version={versions['contract_version']}"
    )


def append_capabilities_jsonl(
    workspace: Path,
    command: str,
    repo_fp: str,
    run_id: str,
    exit_code: int,
    warnings_count: int,
    cap_path: Path,
    metrics: dict,
    layout: str,
    smart_info: dict,
    calibration: Optional[dict] = None,
    hints: Optional[dict] = None,
    hint_bundle: Optional[dict] = None,
    federated_index: Optional[dict] = None,
    layout_details: Optional[dict] = None,
) -> Path:
    """
    Append summary line to workspace-level capabilities.jsonl (append-only).

    Stored under fingerprint workspace root:
      <workspace>/<fp>/capabilities.jsonl
    """
    jsonl_path = workspace.parent / "capabilities.jsonl"
    record = {
        "timestamp": utc_now_iso(),
        "package_version": PACKAGE_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "contract_version": CONTRACT_VERSION,
        "company_scope": company_scope_runtime(),
        "command": command,
        "repo_fp": repo_fp,
        "run_id": run_id,
        "exit_code": int(exit_code),
        "warnings_count": int(warnings_count),
        "capabilities_path": str(cap_path.resolve()),
        "layout": layout,
        "module_candidates": as_int(metrics.get("module_candidates", 0), 0),
        "ambiguity_ratio": float(metrics.get("ambiguity_ratio", 0.0) or 0.0),
        "limits_hit": bool(metrics.get("limits_hit", False)),
        "limits_suggestion": str(metrics.get("limits_suggestion", "")),
        "limits": metrics.get("limits", {"max_files": None, "max_seconds": None}),
        "scan_stats": build_scan_stats(metrics),
        "scan_io_stats": metrics.get("scan_io_stats", {}) if isinstance(metrics.get("scan_io_stats"), dict) else {},
        "scan_graph": metrics.get("scan_graph", {}) if isinstance(metrics.get("scan_graph"), dict) else {},
        "layout_details": layout_details if isinstance(layout_details, dict) else {},
        "smart_reused": bool(smart_info.get("reused", False)),
        "reuse_validated": bool(smart_info.get("reuse_validated", False)),
        "reused_from_run_id": smart_info.get("reused_from_run_id"),
        "hints": hints if isinstance(hints, dict) else {},
        "hint_bundle": hint_bundle if isinstance(hint_bundle, dict) else {},
        "federated_index": federated_index if isinstance(federated_index, dict) else {},
        "calibration": calibration if isinstance(calibration, dict) else {},
        "needs_human_hint": bool((calibration or {}).get("needs_human_hint", False)),
        "confidence_tier": str((calibration or {}).get("confidence_tier", "-")),
        "hint_effective": bool(metrics.get("hint_effective", False)),
        "confidence_delta": float(metrics.get("confidence_delta", 0.0) or 0.0),
        "mismatch_reason": str(metrics.get("mismatch_reason", "-") or "-"),
        "mismatch_detail": str(metrics.get("mismatch_detail", "-") or "-"),
        "mismatch_suggestion": str(metrics.get("mismatch_suggestion", "-") or "-"),
    }
    atomic_append_jsonl(jsonl_path, record)
    return jsonl_path


def emit_capability_contract_lines(
    cap_path: Path,
    command: str,
    fp: str,
    run_id: str,
    smart_info: dict,
    metrics: dict,
    governance: dict,
    workspace: Path,
    exit_code: int,
    warnings_count: int,
    layout: str,
    calibration: Optional[dict] = None,
    hints: Optional[dict] = None,
    hint_bundle: Optional[dict] = None,
    federated_index: Optional[dict] = None,
    layout_details: Optional[dict] = None,
) -> Path:
    """
    Emit stdout/stderr contract outputs and append capabilities.jsonl.

    v4 additions:
      - stdout: HONGZHI_CAPS <abs_path>
      - workspace append-only jsonl summary
    """
    if isinstance(calibration, dict):
        metrics.setdefault("needs_human_hint", bool(calibration.get("needs_human_hint", False)))
        metrics.setdefault("confidence_tier", str(calibration.get("confidence_tier", "-")))
        metrics.setdefault(
            "ambiguity_ratio",
            float(calibration.get("metrics_snapshot", {}).get("ambiguity_ratio", metrics.get("ambiguity_ratio", 0.0)) or 0.0),
        )
    if isinstance(hints, dict):
        metrics.setdefault("hint_applied", bool(hints.get("applied", False)))
        metrics.setdefault("hint_bundle", str(hints.get("bundle_path", "") or "-"))
        metrics.setdefault("hint_effective", bool(hints.get("effective", False)))
        metrics.setdefault("confidence_delta", float(hints.get("confidence_delta", 0.0) or 0.0))
    if isinstance(hint_bundle, dict):
        metrics.setdefault("hint_bundle_kind", str(hint_bundle.get("kind", "") or "-"))
        metrics.setdefault("hint_verified", bool(hint_bundle.get("verified", False)))
        metrics.setdefault("hint_expired", bool(hint_bundle.get("expired", False)))
    metrics.setdefault("mismatch_reason", "-")
    metrics.setdefault("mismatch_detail", "-")
    metrics.setdefault("mismatch_suggestion", "-")
    jsonl_path = append_capabilities_jsonl(
        workspace=workspace,
        command=command,
        repo_fp=fp,
        run_id=run_id,
        exit_code=exit_code,
        warnings_count=warnings_count,
        cap_path=cap_path,
        metrics=metrics,
        layout=layout,
        smart_info=smart_info,
        calibration=calibration,
        hints=hints,
        hint_bundle=hint_bundle,
        federated_index=federated_index,
        layout_details=layout_details,
    )
    print(f"[plugin] capabilities_jsonl: {jsonl_path}", file=sys.stderr)
    print_caps_pointer_line(
        cap_path,
        command=command,
        repo_fingerprint=fp,
        run_id=run_id,
        mismatch_reason=str(metrics.get("mismatch_reason", "-") or "-"),
        mismatch_detail=str(metrics.get("mismatch_detail", "-") or "-"),
        mismatch_suggestion=str(metrics.get("mismatch_suggestion", "-") or "-"),
    )
    if isinstance(hints, dict) and hints.get("emitted") and hints.get("bundle_path"):
        print_hints_pointer_line(
            str(hints.get("bundle_path")),
            command=command,
            repo_fingerprint=fp,
            run_id=run_id,
        )
    print_summary_line(command, fp, run_id, smart_info, metrics, governance)
    return jsonl_path


def resolve_global_state(args, read_only: bool = False) -> Path:
    override = args.global_state_root or os.environ.get(GLOBAL_STATE_ENV)
    try:
        return resolve_global_state_root(override, read_only=read_only)
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)


def find_repo_entry_by_path(index: dict, repo_root: Path) -> Tuple[str | None, dict | None]:
    repo_str = str(repo_root.resolve())
    for fp, entry in index.get("projects", {}).items():
        if isinstance(entry, dict) and entry.get("repo_root") == repo_str:
            return fp, entry
    return None, None


def attempt_smart_reuse(command: str, args, repo_root: Path, fp: str, vcs: dict, ws: Path, global_state_root: Path):
    """
    Decide and materialize smart reuse.

    Returns tuple:
      (smart_info, reused_payload, reasons)
    """
    smart_info = {
        "enabled": bool(args.smart),
        "reused": False,
        "reused_from_run_id": None,
        "reuse_validated": False,
    }
    reused_payload = {}
    reasons = []
    if not args.smart:
        return smart_info, reused_payload, reasons

    index_path = global_state_root / "capability_index.json"
    index = load_capability_index(index_path)
    current_entry = index.get("projects", {}).get(fp)
    source_fp = fp

    if not isinstance(current_entry, dict):
        source_fp, current_entry = find_repo_entry_by_path(index, repo_root)
        if current_entry and args.smart_max_fingerprint_drift == "strict":
            reasons.append("fingerprint drift detected under strict policy")
            return smart_info, reused_payload, reasons

    if not isinstance(current_entry, dict):
        reasons.append("no prior successful run in capability index")
        return smart_info, reused_payload, reasons

    if source_fp != fp:
        reasons.append("WARN: smart reuse skipped because source fingerprint mismatched current run")
        return smart_info, reused_payload, reasons

    last_success = current_entry.get("last_success", {})
    if not isinstance(last_success, dict):
        reasons.append("missing last_success record")
        return smart_info, reused_payload, reasons

    timestamp = parse_iso_ts(last_success.get("timestamp", ""))
    if not timestamp:
        reasons.append("invalid last_success timestamp")
        return smart_info, reused_payload, reasons

    age_s = (datetime.now(timezone.utc) - timestamp).total_seconds()
    if age_s > args.smart_max_age_seconds:
        reasons.append(
            f"last_success too old ({int(age_s)}s > {args.smart_max_age_seconds}s)"
        )
        return smart_info, reused_payload, reasons

    source_vcs = current_entry.get("vcs", {}) if isinstance(current_entry.get("vcs"), dict) else {}
    source_head = source_vcs.get("head")
    current_head = vcs.get("head")
    if source_head and current_head and source_head != current_head:
        if args.smart_max_fingerprint_drift == "strict":
            reasons.append("vcs head changed under strict policy")
            return smart_info, reused_payload, reasons
        reasons.append("WARN: vcs head changed but allowed by non-strict smart policy")

    source_ws = Path(last_success.get("workspace", ""))
    if not source_ws.is_dir():
        reasons.append("source workspace missing")
        return smart_info, reused_payload, reasons

    if not expected_reuse_artifacts_exist(source_ws, command):
        reasons.append("required artifacts missing in source workspace")
        return smart_info, reused_payload, reasons

    source_metrics = current_entry.get("metrics", {}) if isinstance(current_entry.get("metrics"), dict) else {}
    cache_hit_rate = source_metrics.get("cache_hit_rate")
    if cache_hit_rate is None:
        reasons.append("WARN: cache_hit_rate unknown, proceeding with artifact-based reuse")
    else:
        try:
            cache_hit_rate = float(cache_hit_rate)
        except (TypeError, ValueError):
            reasons.append("invalid cache_hit_rate in index")
            return smart_info, reused_payload, reasons
        if cache_hit_rate < args.smart_min_cache_hit:
            reasons.append(
                f"cache_hit_rate below threshold ({cache_hit_rate:.2f} < {args.smart_min_cache_hit:.2f})"
            )
            return smart_info, reused_payload, reasons

    source_command_dir = source_ws / command
    target_command_dir = ws / command
    if source_command_dir.exists():
        link_or_copy_path(source_command_dir, target_command_dir)
    elif command == "discover":
        # Discover must always have a discover dir for downstream checks.
        target_command_dir.mkdir(parents=True, exist_ok=True)

    old_caps = load_workspace_capabilities(source_ws)
    reused_metrics = old_caps.get("metrics", {}) if isinstance(old_caps.get("metrics"), dict) else {}
    reused_roots = old_caps.get("roots", []) if isinstance(old_caps.get("roots"), list) else []
    reused_warnings = old_caps.get("warnings", []) if isinstance(old_caps.get("warnings"), list) else []
    reused_suggestions = old_caps.get("suggestions", []) if isinstance(old_caps.get("suggestions"), list) else []
    reused_layout = old_caps.get("layout", "unknown")
    reused_calibration = old_caps.get("calibration", {}) if isinstance(old_caps.get("calibration"), dict) else {}
    reused_hints = old_caps.get("hints", {}) if isinstance(old_caps.get("hints"), dict) else {}
    reused_hint_bundle = old_caps.get("hint_bundle", {}) if isinstance(old_caps.get("hint_bundle"), dict) else {}
    reused_layout_details = old_caps.get("layout_details", {}) if isinstance(old_caps.get("layout_details"), dict) else {}

    # Force fresh timing to reflect this run while preserving reused metrics.
    reused_metrics["scan_time_s"] = 0.0
    reused_payload = {
        "layout": reused_layout,
        "roots": reused_roots,
        "warnings": reused_warnings,
        "suggestions": reused_suggestions,
        "metrics": reused_metrics,
        "artifacts": collect_command_artifacts(ws, command),
        "source_workspace": str(source_ws),
        "source_fp": source_fp,
        "calibration": reused_calibration,
        "hints": reused_hints,
        "hint_bundle": reused_hint_bundle,
        "layout_details": reused_layout_details,
    }
    smart_info["reused"] = True
    smart_info["reused_from_run_id"] = last_success.get("run_id")
    smart_info["reuse_validated"] = True
    return smart_info, reused_payload, reasons


def write_run_meta(
    global_state_root: Path,
    fp: str,
    run_id: str,
    payload: dict,
) -> Path:
    run_meta_path = global_state_root / fp / "runs" / run_id / "run_meta.json"
    atomic_write_json(run_meta_path, payload)
    return run_meta_path


def update_capability_registry(
    global_state_root: Path,
    fp: str,
    repo_root: Path,
    command: str,
    run_id: str,
    ws: Path,
    vcs: dict,
    metrics: dict,
    modules: dict,
    warnings_list: list,
    suggestions_list: list,
    smart_info: dict,
    governance: dict,
) -> dict:
    index_path = global_state_root / "capability_index.json"
    index = load_capability_index(index_path)
    now_ts = utc_now_iso()
    versions = version_triplet()
    entry_current = index.get("projects", {}).get(fp, {})
    if not isinstance(entry_current, dict):
        entry_current = {}
    created_at = entry_current.get("created_at") or now_ts
    metrics_for_index = dict(metrics)
    # Preserve threshold semantics: absence means unknown; non-positive value is treated as unknown.
    if float(metrics_for_index.get("cache_hit_rate", 0) or 0) <= 0:
        metrics_for_index.pop("cache_hit_rate", None)
    run_summary = {
        "run_id": run_id,
        "timestamp": now_ts,
        "workspace": str(ws),
        "command": command,
        "metrics": {
            "module_candidates": as_int(metrics.get("module_candidates", 0), 0),
            "endpoints_total": as_int(metrics.get("endpoints_total", 0), 0),
            "scan_time_s": float(metrics.get("scan_time_s", 0.0) or 0.0),
            "limits_hit": bool(metrics.get("limits_hit", False)),
            "hint_applied": bool(metrics.get("hint_applied", False)),
            "hints_emitted": bool(metrics.get("hints_emitted", False)),
            "hint_bundle_created": bool(metrics.get("hints_emitted", False)),
            "hint_bundle_kind": str(metrics.get("hint_bundle_kind", "") or ""),
            "hint_bundle_expires_at": str(metrics.get("hint_bundle_expires_at", "") or ""),
            "reuse_validated": bool(smart_info.get("reuse_validated", False)),
        },
    }
    runs = entry_current.get("runs", [])
    if not isinstance(runs, list):
        runs = []
    runs.append(run_summary)
    runs = runs[-50:]
    latest = dict(run_summary)
    entry_patch = {
        "repo_fingerprint": fp,
        "created_at": created_at,
        "latest": latest,
        "runs": runs,
        "versions": {
            "package": versions["package_version"],
            "plugin": versions["plugin_version"],
            "contract": versions["contract_version"],
        },
        "governance": {
            "enabled": bool(governance.get("enabled", False)),
            "token_used": bool(governance.get("token_used", False)),
            "policy_hash": governance.get("policy_hash", ""),
        },
        "repo_root": str(repo_root),
        "vcs": {"kind": vcs.get("kind", "none"), "head": vcs.get("head", "none")},
        "last_success": latest,
        "metrics": metrics_for_index,
        "modules": modules,
        "warnings": warnings_list,
        "suggestions": suggestions_list,
    }
    index = update_project_entry(index, fp, entry_patch)
    save_capability_index(index_path, index)
    latest_path = write_latest_pointer(global_state_root, fp, run_id, str(ws))
    run_meta_path = write_run_meta(
        global_state_root,
        fp,
        run_id,
        {
            "version": "1.0.0",
            "timestamp": now_ts,
            "repo_fingerprint": fp,
            "repo_root": str(repo_root),
            "workspace": str(ws),
            "command": command,
            "vcs": {"kind": vcs.get("kind", "none"), "head": vcs.get("head", "none")},
            "smart": smart_info,
            "hints": {
                "applied": bool(metrics.get("hint_applied", False)),
                "emitted": bool(metrics.get("hints_emitted", False)),
                "bundle_path": str(metrics.get("hint_bundle", "") or ""),
                "bundle_kind": str(metrics.get("hint_bundle_kind", "") or ""),
                "bundle_expires_at": str(metrics.get("hint_bundle_expires_at", "") or ""),
                "bundle_verified": bool(metrics.get("hint_verified", False)),
                "bundle_expired": bool(metrics.get("hint_expired", False)),
            },
            "governance": governance,
            "versions": versions,
            "metrics": metrics,
            "modules": modules,
        },
    )
    return {
        "global_state_root": str(global_state_root),
        "index_path": str(index_path),
        "latest_path": str(latest_path),
        "run_meta_path": str(run_meta_path),
        "updated": True,
    }


def update_federated_registry(
    *,
    global_state_root: Path,
    repo_root: Path,
    fp: str,
    command: str,
    run_id: str,
    ws: Path,
    metrics: dict,
    layout: str,
    governance: dict,
    capability_registry: dict,
) -> dict:
    fed_path = global_state_root / "federated_index.json"
    fed_jsonl = global_state_root / "federated_index.jsonl"
    fed = load_federated_index(fed_path)
    now_ts = utc_now_iso()
    versions_triplet = version_triplet()
    versions = {
        "package": versions_triplet["package_version"],
        "plugin": versions_triplet["plugin_version"],
        "contract": versions_triplet["contract_version"],
    }
    latest_pointer = {
        "run_id": run_id,
        "timestamp": now_ts,
        "workspace": str(ws),
        "capability_latest_path": str(capability_registry.get("latest_path", "")),
        "command": command,
    }
    run_record = build_run_record(
        command=command,
        run_id=run_id,
        timestamp=now_ts,
        workspace=str(ws),
        latest_path=str(capability_registry.get("latest_path", "")),
        layout=layout,
        metrics=metrics,
        versions=versions,
        governance=governance,
    )
    fed = update_federated_repo_entry(
        index=fed,
        repo_fp=fp,
        repo_root=str(repo_root),
        latest_pointer=latest_pointer,
        run_record=run_record,
        governance=governance,
        versions=versions,
    )
    save_federated_index(fed_path, fed)
    if bool(governance.get("federated_index_write_jsonl", True)):
        atomic_append_jsonl(
            fed_jsonl,
            {
                "timestamp": now_ts,
                "repo_fp": fp,
                "command": command,
                "run_id": run_id,
                "layout": layout,
                "limits_hit": bool(metrics.get("limits_hit", False)),
                "hint_bundle_created": bool(metrics.get("hints_emitted", False)),
            },
        )
    mirror_path = ""
    if bool(governance.get("federated_index_write_repo_mirror", True)):
        entry = fed.get("repos", {}).get(fp, {}) if isinstance(fed.get("repos"), dict) else {}
        mirror = write_repo_mirror(global_state_root, fp, entry)
        mirror_path = str(mirror)
    return {
        "path": str(fed_path),
        "jsonl_path": str(fed_jsonl),
        "mirror_path": mirror_path,
        "updated": True,
    }


def maybe_update_federated_registry(
    *,
    command: str,
    args,
    final_exit_code: int,
    global_state_root: Path,
    repo_root: Path,
    fp: str,
    run_id: str,
    ws: Path,
    metrics: dict,
    layout: str,
    governance: dict,
    capability_registry: dict,
    warnings_list: list,
) -> Tuple[int, dict]:
    federated_registry = {
        "path": str(global_state_root / "federated_index.json"),
        "jsonl_path": str(global_state_root / "federated_index.jsonl"),
        "mirror_path": "",
        "updated": False,
        "blocked_reason": "",
    }
    if final_exit_code != 0:
        return final_exit_code, federated_registry

    if not federated_index_policy_enabled(governance):
        federated_registry["blocked_reason"] = "disabled_by_policy"
        warnings_list.append("federated_index_blocked: disabled_by_policy")
        print("[plugin] WARN: federated index disabled by policy", file=sys.stderr)
        return final_exit_code, federated_registry

    scope_ok, scope_reason = federated_index_scope_allowed(governance)
    if not scope_ok:
        federated_registry["blocked_reason"] = scope_reason
        warnings_list.append(f"federated_index_blocked: {scope_reason}")
        print(f"[plugin] WARN: federated index blocked: {scope_reason}", file=sys.stderr)
        print_index_block_line(
            code=INDEX_SCOPE_EXIT_CODE,
            reason=scope_reason,
            command=command,
            detail="federated index write blocked by token scope",
            token_scope=normalize_scope(governance.get("token_scope")),
        )
        if args.strict:
            metrics["exit_hint"] = "federated_index_scope_missing"
            return INDEX_SCOPE_EXIT_CODE, federated_registry
        return final_exit_code, federated_registry

    federated_registry = update_federated_registry(
        global_state_root=global_state_root,
        repo_root=repo_root,
        fp=fp,
        command=command,
        run_id=run_id,
        ws=ws,
        metrics=metrics,
        layout=layout,
        governance=governance,
        capability_registry=capability_registry,
    )
    return final_exit_code, federated_registry


def extract_modules_summary(
    repo_root: Path,
    candidates: List[dict],
    module_endpoints: Dict[str, int],
) -> Dict[str, dict]:
    modules = {}
    for idx, candidate in enumerate(candidates):
        module_key = candidate.get("module_key")
        if not module_key:
            continue
        confidence = candidate.get("confidence")
        if confidence is None:
            try:
                import auto_module_discover as amd  # local script import

                confidence = amd.compute_confidence(candidates, idx)
            except Exception:
                confidence = 0
        roots = []
        package_prefix = candidate.get("package_prefix", "")
        if package_prefix:
            roots.append(f"src/main/java/{package_prefix.replace('.', '/')}")
        modules[module_key] = {
            "package_prefix": package_prefix,
            "confidence": round(float(confidence), 4) if confidence is not None else 0,
            "roots": roots,
            "endpoints": int(module_endpoints.get(module_key, 0)),
        }
    # Normalize roots for readability
    for module_data in modules.values():
        module_data["roots"] = [normalize_rel(r, repo_root) for r in module_data.get("roots", [])]
    return modules


# ═══════════════════════════════════════════════════════════════════════════════
#  Layout detection
# ═══════════════════════════════════════════════════════════════════════════════

def detect_layout(repo_root):
    """Detect project layout: multi-module maven, single module, legacy."""
    root_pom = repo_root / "pom.xml"
    if root_pom.exists():
        try:
            text = root_pom.read_text(encoding="utf-8", errors="ignore")
            if "<modules>" in text:
                return "multi-module-maven"
        except OSError:
            pass
        return "single-module-maven"
    if (repo_root / "build.gradle").exists() or (repo_root / "build.gradle.kts").exists():
        return "gradle"
    if (repo_root / "src" / "main" / "java").is_dir():
        return "single-module-java"
    return "unknown"


def _fallback_calibration_report(workspace: Path) -> dict:
    """Minimal fallback when calibration_engine module cannot be imported."""
    calibration_dir = workspace / "calibration"
    calibration_dir.mkdir(parents=True, exist_ok=True)
    report_json = calibration_dir / "calibration_report.json"
    report_md = calibration_dir / "calibration_report.md"
    payload = {
        "version": "1.0.0",
        "timestamp": utc_now_iso(),
        "needs_human_hint": False,
        "confidence": 1.0,
        "confidence_tier": "high",
        "reasons": [],
        "action_suggestions": ["calibration_engine import failed; fallback report used"],
        "suggested_hints": {"identity": {"backend_package_hint": "", "web_path_hint": "", "keywords": []}},
        "metrics_snapshot": {},
        "report_path": str(report_md),
        "report_json_path": str(report_json),
        "suggested_hints_path": "",
    }
    atomic_write_json(report_json, payload)
    report_md.write_text(
        "# Calibration Report\n\n- fallback: calibration_engine unavailable\n"
        f"- generated_at: `{payload['timestamp']}`\n",
        encoding="utf-8",
    )
    return payload


def run_discover_calibration(
    workspace: Path,
    candidates: List[dict],
    metrics: dict,
    roots_info: List[dict],
    structure_signals: dict,
    keywords: List[str],
    min_confidence: float,
    ambiguity_threshold: float,
    emit_hints: bool,
) -> dict:
    """
    Execute Round20 calibration layer and return machine-readable report.

    The import is delayed to avoid runtime breakage in environments where this
    module is not packaged; discover still remains functional with fallback.
    """
    try:
        import calibration_engine as ce  # local script in prompt-dsl-system/tools

        report = ce.run_calibration(
            workspace=workspace,
            candidates=candidates,
            metrics=metrics,
            roots_info=roots_info,
            structure_signals=structure_signals,
            keywords=keywords,
            min_confidence=min_confidence,
            ambiguity_threshold=ambiguity_threshold,
            emit_hints=emit_hints,
        )
        if isinstance(report, dict):
            return report
    except Exception as exc:
        print(f"[plugin] WARN: calibration_engine failed: {exc}", file=sys.stderr)
    return _fallback_calibration_report(workspace)


# ═══════════════════════════════════════════════════════════════════════════════
#  Subcommand: discover
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_discover(args):
    """Auto-discover modules, roots, structure, endpoints."""
    repo_root = Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        print(f"FAIL: repo-root not found: {repo_root}", file=sys.stderr)
        sys.exit(1)

    fp = compute_project_fingerprint(repo_root)
    run_id = utc_now_run_id()
    ws = resolve_workspace(fp, run_id, args.workspace_root)
    global_state_root = resolve_global_state(args)
    vcs = detect_vcs_info(repo_root)
    assert_output_roots_safe(repo_root, ws, global_state_root)
    disc_dir = ws / "discover"
    disc_dir.mkdir(parents=True, exist_ok=True)

    layout = detect_layout(repo_root)
    warnings_list = []
    suggestions_list = []
    artifacts_list = []
    metrics = {}
    modules_summary = {}
    roots_info = []
    ambiguity_ratio = 0.0
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else []
    hint_state = default_hint_state(getattr(args, "apply_hints", ""), getattr(args, "hint_strategy", "conservative"))
    hint_bundle_info = default_hint_bundle_info()
    final_exit_code = 0
    if args.apply_hints:
        loaded_hints = load_hint_bundle_input(str(args.apply_hints))
        if loaded_hints.get("ok"):
            verify = verify_hint_bundle(
                loaded_hints.get("payload", {}),
                repo_fingerprint=fp,
                command="discover",
                allow_cross_repo_hints=bool(getattr(args, "allow_cross_repo_hints", False)),
            )
            hint_bundle_info.update(
                {
                    "kind": str(verify.get("kind", "") or ""),
                    "path": str(loaded_hints.get("source_path", "") or ""),
                    "verified": bool(verify.get("verified", False)),
                    "expired": bool(verify.get("expired", False)),
                    "ttl_seconds": int(verify.get("ttl_seconds", 0) or 0),
                    "created_at": str(verify.get("created_at", "") or ""),
                    "expires_at": str(verify.get("expires_at", "") or ""),
                }
            )
            if verify.get("ok"):
                hint_state["applied"] = True
                hint_state["verified"] = True
                hint_state["expired"] = False
                hint_state["kind"] = str(verify.get("kind", "") or "")
                hint_state["source_path"] = str(loaded_hints.get("source_path", "") or "")
                hint_state["identity"] = verify.get("identity", hint_state["identity"])
                hint_state["roots_hints"] = verify.get("roots_hints", hint_state["roots_hints"])
                hint_state["layout_hints"] = verify.get("layout_hints", hint_state["layout_hints"])
                hint_state["ttl_seconds"] = int(verify.get("ttl_seconds", 0) or 0)
                hint_state["created_at"] = str(verify.get("created_at", "") or "")
                hint_state["expires_at"] = str(verify.get("expires_at", "") or "")
                keywords = merge_keywords(
                    keywords,
                    hint_state["identity"].get("keywords", []),
                    hint_state["strategy"],
                )
            else:
                reason = str(verify.get("error", "hint_verify_failed") or "hint_verify_failed")
                warnings_list.append(f"apply_hints_failed: {reason}")
                print(f"[plugin] WARN: apply_hints failed: {reason}", file=sys.stderr)
                if reason == "hint_bundle_expired":
                    hint_state["expired"] = True
                    hint_bundle_info["expired"] = True
                    if args.strict:
                        final_exit_code = HINT_VERIFY_EXIT_CODE
                        metrics["exit_hint"] = "hint_bundle_expired"
                elif args.strict:
                    final_exit_code = HINT_VERIFY_EXIT_CODE
                    metrics["exit_hint"] = "hint_verify_failed"
        else:
            warnings_list.append(f"apply_hints_failed: {loaded_hints.get('error', 'unknown')}")
            print(
                f"[plugin] WARN: apply_hints failed for {args.apply_hints}: "
                f"{loaded_hints.get('error', 'unknown')}",
                file=sys.stderr,
            )
            if args.strict:
                final_exit_code = HINT_VERIFY_EXIT_CODE
                metrics["exit_hint"] = "hint_verify_failed"
    hinted_layout = str(hint_state.get("layout_hints", {}).get("layout", "") or "").strip()
    if hinted_layout:
        layout = hinted_layout
    layout_details = {
        "adapter_used": "layout_adapters_v1",
        "candidates_scanned": 0,
        "java_roots_detected": 0,
        "template_roots_detected": 0,
        "keywords_used": len(keywords),
        "hint_identity_present": bool(hint_state.get("identity")),
        "fallback_reason": "",
    }
    discover_candidates: List[dict] = []
    calibration_report: dict = {
        "needs_human_hint": False,
        "confidence": 1.0,
        "confidence_tier": "high",
        "reasons": [],
        "suggested_hints_path": "",
        "report_path": "",
        "report_json_path": "",
        "suggested_hints": {"identity": {"backend_package_hint": "", "web_path_hint": "", "keywords": []}},
        "action_suggestions": [],
        "metrics_snapshot": {},
    }
    structure_signals = {
        "controller_count": 0,
        "service_count": 0,
        "repository_count": 0,
        "template_count": 0,
        "endpoint_count": 0,
        "endpoint_paths": [],
        "templates": [],
        "modules": {},
    }
    scan_graph_mismatch_detected = False
    scan_graph_mismatch_reason = "-"
    scan_graph_mismatch_detail = "-"
    smart_info = {
        "enabled": bool(args.smart),
        "reused": False,
        "reused_from_run_id": None,
        "reuse_validated": False,
    }
    capability_registry = {
        "global_state_root": str(global_state_root),
        "index_path": str(global_state_root / "capability_index.json"),
        "latest_path": "",
        "run_meta_path": "",
        "updated": False,
    }
    federated_registry = {
        "path": str(global_state_root / "federated_index.json"),
        "jsonl_path": str(global_state_root / "federated_index.jsonl"),
        "mirror_path": "",
        "updated": False,
        "blocked_reason": "",
    }
    all_java_results: List[dict] = []
    all_templates: List[str] = []
    # Snapshot before
    snap_before = take_snapshot(repo_root)

    t_start = time.time()
    smart_info, reused_payload, smart_reasons = attempt_smart_reuse(
        "discover", args, repo_root, fp, vcs, ws, global_state_root
    )
    for reason in smart_reasons:
        if reason.startswith("WARN:"):
            warnings_list.append(reason[5:].strip())
            print(f"[plugin] WARN: {reason[5:].strip()}", file=sys.stderr)
        elif args.smart and not smart_info.get("reused"):
            print(f"[plugin] smart-skip: {reason}", file=sys.stderr)

    if smart_info.get("reused"):
        layout = reused_payload.get("layout", layout)
        roots_info = reused_payload.get("roots", [])
        artifacts_list = reused_payload.get("artifacts", [])
        metrics = reused_payload.get("metrics", {})
        warnings_list.extend(reused_payload.get("warnings", []))
        suggestions_list.extend(reused_payload.get("suggestions", []))
        index_snapshot = load_capability_index(global_state_root / "capability_index.json")
        source_fp = reused_payload.get("source_fp", fp)
        source_entry = index_snapshot.get("projects", {}).get(source_fp, {})
        if isinstance(source_entry, dict):
            modules_summary = source_entry.get("modules", {}) if isinstance(source_entry.get("modules"), dict) else {}
        metrics.setdefault("module_candidates", len(roots_info))
        metrics.setdefault("cache_hit_rate", 1.0)
        discover_candidates = [
            {
                "module_key": r.get("module_key"),
                "package_prefix": r.get("package_prefix"),
                "score": 1.0,
                "confidence": 1.0,
            }
            for r in roots_info
            if isinstance(r, dict)
        ]
        calibration_seed = reused_payload.get("calibration", {})
        if isinstance(calibration_seed, dict):
            calibration_report.update(calibration_seed)
        hints_seed = reused_payload.get("hints", {})
        if isinstance(hints_seed, dict):
            hint_state.update(hints_seed)
        hint_bundle_seed = reused_payload.get("hint_bundle", {})
        if isinstance(hint_bundle_seed, dict):
            hint_bundle_info.update(hint_bundle_seed)
        layout_details_seed = reused_payload.get("layout_details", {})
        if isinstance(layout_details_seed, dict):
            layout_details.update(layout_details_seed)
        ensure_endpoints_total(metrics)
    else:
        module_endpoints = {}

        # ── Step 1: auto_module_discover ──
        sys.path.insert(0, str(SCRIPT_DIR))
        adapter_pre = {
            "layout": layout,
            "java_roots": [],
            "template_roots": [],
            "layout_details": {},
        }
        try:
            import auto_module_discover as amd

            adapter_pre = run_layout_adapters(
                repo_root=repo_root,
                candidates=[],
                keywords=keywords,
                hint_identity=hint_state.get("identity", {}),
                fallback_layout=layout,
            )
            metrics["layout_adapter_runs"] = 1
            pre_java_roots = [Path(p) for p in adapter_pre.get("java_roots", []) if Path(p).is_dir()]
            pre_template_roots = [Path(p) for p in adapter_pre.get("template_roots", []) if Path(p).is_dir()]
            hinted_backend_roots = hint_state.get("roots_hints", {}).get("backend_java", [])
            if isinstance(hinted_backend_roots, list):
                for rel in hinted_backend_roots:
                    root_hint = (repo_root / str(rel)).resolve()
                    if root_hint.is_dir() and root_hint not in pre_java_roots:
                        pre_java_roots.append(root_hint)
            hinted_template_roots = hint_state.get("roots_hints", {}).get("web_template", [])
            if isinstance(hinted_template_roots, list):
                for rel in hinted_template_roots:
                    tpl_hint = (repo_root / str(rel)).resolve()
                    if tpl_hint.is_dir() and tpl_hint not in pre_template_roots:
                        pre_template_roots.append(tpl_hint)
            if not pre_java_roots:
                pre_java_roots = amd.find_java_roots(repo_root)
            java_roots = pre_java_roots
            adapter_java_roots = list(pre_java_roots)
            adapter_template_roots = list(pre_template_roots)
            all_pkgs = {}
            for jr in java_roots:
                for pkg, stats in amd.scan_packages(jr).items():
                    if pkg not in all_pkgs:
                        all_pkgs[pkg] = {"files": 0, "controllers": 0, "services": 0, "repositories": 0}
                    for k in ("files", "controllers", "services", "repositories"):
                        all_pkgs[pkg][k] += stats[k]
            candidates = sort_candidates_stable(amd.cluster_modules(all_pkgs, keywords)[: args.top_k])
            pre_hint_conf = amd.compute_confidence(candidates, 0) if candidates else 0.0
            pre_hint_top_score = float(candidates[0].get("score", 0.0) or 0.0) if candidates else 0.0
            if hint_state.get("applied"):
                candidates = sort_candidates_stable(
                    apply_hint_boost_to_candidates(
                        candidates,
                        hint_state.get("identity", {}),
                        hint_state.get("strategy", "conservative"),
                    )
                )
            post_hint_conf = amd.compute_confidence(candidates, 0) if candidates else 0.0
            post_hint_top_score = float(candidates[0].get("score", 0.0) or 0.0) if candidates else 0.0
            hint_delta = round(float(post_hint_conf) - float(pre_hint_conf), 4)
            score_delta = round(float(post_hint_top_score) - float(pre_hint_top_score), 4)
            metrics["hint_confidence_pre"] = round(float(pre_hint_conf), 4)
            metrics["hint_confidence_post"] = round(float(post_hint_conf), 4)
            metrics["confidence_delta"] = hint_delta
            metrics["hint_score_delta"] = score_delta
            discover_candidates = candidates
            for i, c in enumerate(candidates):
                c["confidence"] = amd.compute_confidence(candidates, i) if candidates else 0
            metrics["candidates"] = sort_candidates_stable(
                [
                    {
                        "module_key": c.get("module_key"),
                        "package_prefix": c.get("package_prefix"),
                        "score": c.get("score"),
                        "confidence": c.get("confidence"),
                        "file_count": c.get("file_count"),
                        "controller_count": c.get("controller_count"),
                        "service_count": c.get("service_count"),
                        "repository_count": c.get("repository_count"),
                    }
                    for c in candidates
                    if isinstance(c, dict)
                ]
            )
        except Exception as e:
            print(f"[plugin] WARN: auto_module_discover failed: {e}", file=sys.stderr)
            candidates = []
            discover_candidates = []
            java_roots = []
            adapter_java_roots = []
            adapter_template_roots = []
            all_pkgs = {}

        metrics["java_roots"] = len(java_roots)
        metrics["module_candidates"] = len(candidates)
        metrics["total_packages"] = len(all_pkgs)
        layout = adapter_pre.get("layout", layout) if isinstance(adapter_pre, dict) else layout
        hinted_layout = str(hint_state.get("layout_hints", {}).get("layout", "") or "").strip()
        if hinted_layout:
            layout = hinted_layout
        adapter_roots_entries = build_roots_entries_from_detected_roots(
            repo_root=repo_root,
            candidates=candidates[:5],
            java_roots=adapter_java_roots,
            template_roots=adapter_template_roots,
        )
        adapter_details = adapter_pre.get("layout_details", {}) if isinstance(adapter_pre.get("layout_details"), dict) else {}
        if adapter_details:
            layout_details.update(adapter_details)
        layout_details["candidates_scanned"] = len(candidates)

        # ── Self-check: ambiguity metrics (warning-only; strict handled by calibration) ──
        if len(candidates) >= 2:
            top_score = float(candidates[0].get("score", 0.0) or 0.0)
            second_score = float(candidates[1].get("score", 0.0) or 0.0)
            metrics["top1_score"] = round(top_score, 4)
            metrics["top2_score"] = round(second_score, 4)
            if top_score > 0:
                ratio = second_score / top_score
                ambiguity_ratio = float(ratio)
                metrics["top2_score_ratio"] = round(float(ratio), 4)
                metrics["ambiguity_ratio"] = round(float(ratio), 4)
                if ratio >= args.ambiguity_threshold and not keywords:
                    warn = (
                        f"ambiguous modules: top2 score ratio={ratio:.2f} "
                        f"(provide --keywords to disambiguate)"
                    )
                    warnings_list.append(warn)
                    print(f"[plugin] WARN: {warn}", file=sys.stderr)
        else:
            metrics["top1_score"] = float(candidates[0].get("score", 0.0) or 0.0) if candidates else 0.0
            metrics["top2_score"] = 0.0
            metrics["top2_score_ratio"] = 0.0

        # Write candidates
        cand_path = disc_dir / "auto_discover.yaml"
        lines = [
            "# Auto-generated by hongzhi_plugin.py discover",
            f"# layout: {layout}",
            f"# candidates: {len(candidates)}",
            "",
            "module_candidates:",
        ]
        for c in candidates:
            lines.append(f'  - module_key: "{c["module_key"]}"')
            lines.append(f'    package_prefix: "{c["package_prefix"]}"')
            lines.append(f"    file_count: {c['file_count']}")
            lines.append(f"    controller_count: {c['controller_count']}")
            lines.append(f"    service_count: {c['service_count']}")
            lines.append(f"    score: {c['score']}")
            lines.append(f"    confidence: {c.get('confidence', 0)}")
        cand_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        artifacts_list.append(str(cand_path))

        # ── Step 2: structure_discover for top candidates ──
        try:
            import structure_discover as sd
        except ImportError:
            sd = None

        all_java_results = []
        all_templates = []
        total_ch = 0
        total_cm = 0
        if sd and candidates:
            # Build unified scan graph once, then reuse its indexed outputs.
            if adapter_java_roots or adapter_template_roots:
                sd_java_roots, sd_template_roots = adapter_java_roots, adapter_template_roots
            else:
                sd_java_roots, sd_template_roots = sd.find_scan_roots(repo_root)

            roots_for_graph = resolve_scan_graph_roots(repo_root, sd_java_roots, sd_template_roots)
            scan_graph_payload, scan_graph_path = build_discover_scan_graph(
                repo_root=repo_root,
                workspace=ws,
                roots=roots_for_graph,
                keywords=keywords,
                max_files=args.max_files,
                max_seconds=args.max_seconds,
                producer_versions=version_triplet(),
            )
            artifacts_list.append(str(scan_graph_path))

            all_java_results, all_templates, scan_graph_io = scan_graph_to_structure_inputs(scan_graph_payload)
            raw_scan_java_results = list(all_java_results)
            total_ch = int(scan_graph_io.get("cache_hit_files", 0) or 0)
            total_cm = int(scan_graph_io.get("cache_miss_files", len(all_java_results)) or 0)
            metrics["cache_hit_files"] = total_ch
            metrics["cache_miss_files"] = total_cm
            metrics["total_scanned_files"] = int(scan_graph_io.get("files_indexed", len(all_java_results)) or 0)
            metrics["cache_hit_rate"] = float(scan_graph_io.get("cache_hit_rate", 0.0) or 0.0)
            if bool(scan_graph_payload.get("limits_hit", False)):
                lr = str(scan_graph_payload.get("limits_reason", "") or "")
                if lr == "max_files" and args.max_files is not None:
                    metrics["files_scanned"] = int(args.max_files) + 1
                metrics["scan_graph_limits_reason"] = lr
            metrics["scan_graph"] = {
                "used": True,
                "cache_key": str(scan_graph_payload.get("cache_key", "")),
                "cache_hit_rate": float(scan_graph_io.get("cache_hit_rate", 0.0) or 0.0),
                "cache_source": str(scan_graph_payload.get("cache_source", "none")),
                "cache_path": str(scan_graph_payload.get("cache_path", "")),
                "path": str(scan_graph_path),
                "java_files_indexed": int(scan_graph_io.get("java_scanned", 0) or 0),
                "bytes_read": int(scan_graph_io.get("bytes_read", 0) or 0),
                "limits_hit": bool(scan_graph_payload.get("limits_hit", False)),
                "limits_reason": str(scan_graph_payload.get("limits_reason", "") or ""),
                "io_stats": scan_graph_io,
            }
            sg_ok, sg_reason, sg_detail = analyze_scan_graph_payload(
                scan_graph_payload,
                expected_schema_version=SCAN_GRAPH_SCHEMA_VERSION,
                expected_producer_versions=version_triplet(),
            )
            metrics["scan_graph"].update(
                {
                    "schema_version": str(scan_graph_payload.get("schema_version", "") or ""),
                    "graph_fingerprint": str(scan_graph_payload.get("graph_fingerprint", "") or ""),
                    "producer_versions": scan_graph_payload.get("producer_versions", {}),
                    "validation_ok": bool(sg_ok),
                    "validation_reason": str(sg_reason or ""),
                }
            )
            if not sg_ok:
                scan_graph_mismatch_detected = True
                scan_graph_mismatch_reason = normalize_mismatch_reason(sg_reason)
                scan_graph_mismatch_detail = str(sg_detail or "scan_graph_payload_invalid")
                warn = f"scan_graph mismatch detected: reason={scan_graph_mismatch_reason}"
                warnings_list.append(warn)
                print(f"[plugin] WARN: {warn}", file=sys.stderr)

            # Endpoint fallback for files marked uncertain / zero-endpoint controllers.
            endpoint_fallback_files = 0
            for i, java_item in enumerate(all_java_results):
                if not isinstance(java_item, dict):
                    continue
                rel_path = str(java_item.get("rel_path", "") or "")
                if not rel_path:
                    continue
                should_refresh = bool(java_item.get("parse_uncertain", False))
                if java_item.get("is_controller") and len(java_item.get("endpoint_signatures", [])) == 0:
                    should_refresh = True
                if not should_refresh:
                    continue
                src_file = repo_root / rel_path
                if not src_file.is_file():
                    continue
                try:
                    refreshed = sd.scan_java_file(src_file, repo_root)
                except Exception:
                    continue
                old_ep = len(java_item.get("endpoint_signatures", []))
                new_ep = len(refreshed.get("endpoint_signatures", []))
                if new_ep >= old_ep:
                    all_java_results[i] = refreshed
                    endpoint_fallback_files += 1
            if isinstance(metrics.get("scan_graph"), dict):
                metrics["scan_graph"]["endpoint_fallback_files"] = endpoint_fallback_files

            # Lightweight self-check: compare scan_graph lite hints with full parser sample.
            spot = scan_graph_spot_check(repo_root, raw_scan_java_results, sample_size=8)
            mismatch_count = int(spot.get("mismatches", 0) or 0)
            mismatch_ratio = float(spot.get("ratio", 0.0) or 0.0)
            metrics["scan_graph_spot_check"] = spot
            if isinstance(metrics.get("scan_graph"), dict):
                metrics["scan_graph"]["spot_check"] = {
                    "sampled": int(spot.get("sampled", 0) or 0),
                    "mismatches": mismatch_count,
                    "ratio": mismatch_ratio,
                }
            if mismatch_count > 0:
                scan_graph_mismatch_detected = True
                if scan_graph_mismatch_reason == "-":
                    scan_graph_mismatch_reason = normalize_mismatch_reason("unknown")
                if scan_graph_mismatch_detail in {"", "-"}:
                    scan_graph_mismatch_detail = ",".join(spot.get("details", [])[:3]) if isinstance(spot.get("details"), list) else "scan_graph_spot_check_mismatch"
                warn = f"scan_graph mismatch detected: mismatches={mismatch_count}, ratio={mismatch_ratio:.2f}"
                warnings_list.append(warn)
                print(f"[plugin] WARN: {warn}", file=sys.stderr)

            clusters = sd.cluster_packages(all_java_results)

            # Per top candidate, extract structure
            for c in candidates[: min(3, len(candidates))]:
                mk = c["module_key"]
                mc = [cl for cl in clusters if mk.lower() in cl["prefix"].lower()]
                prefix_filter = mc[0]["prefix"] if mc else None
                ep_sigs = sd.collect_endpoint_signatures(
                    all_java_results, module_key=mk, prefix_filter=prefix_filter
                )
                mod_tpls = [t for t in all_templates if mk.lower() in t.lower()]

                # Self-check: controllers but no endpoints
                ctrl_count = c.get("controller_count", 0)
                if ctrl_count > 0 and len(ep_sigs) == 0:
                    symbolic_retry_files = 0
                    mk_lower = str(mk).lower()
                    for i, java_item in enumerate(all_java_results):
                        if not isinstance(java_item, dict):
                            continue
                        rel_path = str(java_item.get("rel_path", "") or "")
                        if not rel_path:
                            continue
                        rel_norm = rel_path.replace("\\", "/").lower()
                        pkg_norm = str(java_item.get("package", "") or "").lower()
                        if mk_lower not in rel_norm and mk_lower not in pkg_norm:
                            continue
                        if isinstance(java_item.get("endpoint_signatures"), list) and java_item.get("endpoint_signatures"):
                            continue
                        # Composed annotations and symbolic constants often live outside controller classes.
                        if "/annotation/" not in rel_norm and "mapping" not in rel_norm:
                            continue
                        src_file = repo_root / rel_path
                        if not src_file.is_file():
                            continue
                        try:
                            refreshed = sd.scan_java_file(src_file, repo_root)
                        except Exception:
                            continue
                        refreshed_eps = refreshed.get("endpoint_signatures", [])
                        if isinstance(refreshed_eps, list) and refreshed_eps:
                            all_java_results[i] = refreshed
                            symbolic_retry_files += 1
                    if symbolic_retry_files > 0:
                        ep_sigs = sd.collect_endpoint_signatures(
                            all_java_results, module_key=mk, prefix_filter=prefix_filter
                        )
                        if isinstance(metrics.get("scan_graph"), dict):
                            metrics["scan_graph"]["endpoint_symbolic_retry_files"] = int(symbolic_retry_files)
                if ctrl_count > 0 and len(ep_sigs) == 0:
                    warn = f"module '{mk}': {ctrl_count} controller(s) but 0 endpoints — possible parsing miss"
                    warnings_list.append(warn)
                    print(f"[plugin] WARN: {warn}", file=sys.stderr)

                struct_path = disc_dir / f"{mk}.structure.yaml"
                all_paths = [r["rel_path"] for r in all_java_results if isinstance(r, dict) and r.get("rel_path")] + all_templates
                fp_data = sd.compute_fingerprint(repo_root, all_paths)
                sd.write_structure_discovered(
                    struct_path,
                    "auto",
                    mk,
                    mc if mc else clusters,
                    ep_sigs,
                    mod_tpls,
                    fp_data,
                    0,
                    total_ch,
                    total_cm,
                    read_only=False,
                )
                artifacts_list.append(str(struct_path))
                module_endpoints[mk] = len(ep_sigs)
                metrics[f"endpoints_{mk}"] = len(ep_sigs)
                structure_signals["controller_count"] += int(c.get("controller_count", 0) or 0)
                structure_signals["service_count"] += int(c.get("service_count", 0) or 0)
                structure_signals["repository_count"] += int(c.get("repository_count", 0) or 0)
                structure_signals["template_count"] += len(mod_tpls)
                structure_signals["endpoint_count"] += len(ep_sigs)
                structure_signals["endpoint_paths"].extend(
                    [str(ep.get("path", "")) for ep in ep_sigs if isinstance(ep, dict) and ep.get("path")]
                )
                structure_signals["templates"].extend(mod_tpls)
                structure_signals["modules"][mk] = {
                    "controller_count": int(c.get("controller_count", 0) or 0),
                    "service_count": int(c.get("service_count", 0) or 0),
                    "repository_count": int(c.get("repository_count", 0) or 0),
                    "template_count": len(mod_tpls),
                    "endpoint_count": len(ep_sigs),
                }
        else:
            metrics["cache_hit_files"] = 0
            metrics["cache_miss_files"] = 0
            metrics["total_scanned_files"] = 0
            metrics["cache_hit_rate"] = 0.0
            metrics["scan_graph"] = {"used": False}

        ensure_endpoints_total(metrics)
        if not structure_signals["controller_count"] and candidates:
            structure_signals["controller_count"] = sum(int(c.get("controller_count", 0) or 0) for c in candidates[:3])
            structure_signals["service_count"] = sum(int(c.get("service_count", 0) or 0) for c in candidates[:3])
            structure_signals["repository_count"] = sum(int(c.get("repository_count", 0) or 0) for c in candidates[:3])
            structure_signals["endpoint_count"] = int(metrics.get("endpoints_total", 0) or 0)
        structure_signals["endpoint_paths"] = list(dict.fromkeys(structure_signals["endpoint_paths"]))
        structure_signals["templates"] = list(dict.fromkeys(structure_signals["templates"]))
        if adapter_roots_entries:
            roots_info = adapter_roots_entries[:5]
        else:
            roots_info = [
                {"module_key": c.get("module_key"), "package_prefix": c.get("package_prefix")}
                for c in candidates[:5]
            ]
        modules_summary = extract_modules_summary(repo_root, candidates[:5], module_endpoints)
        if roots_info:
            for root_entry in roots_info:
                if not isinstance(root_entry, dict):
                    continue
                mk = root_entry.get("module_key")
                if mk in modules_summary and isinstance(modules_summary[mk], dict):
                    roots_block = root_entry.get("roots", [])
                    if isinstance(roots_block, list) and roots_block:
                        modules_summary[mk]["roots"] = [
                            str(item.get("path", "")) for item in roots_block
                            if isinstance(item, dict) and item.get("path")
                        ]

    scan_time = time.time() - t_start
    metrics["scan_time_s"] = round(scan_time, 3)
    metrics["layout"] = layout
    metrics["layout_details"] = layout_details
    metrics["hint_applied"] = bool(hint_state.get("applied", False))
    metrics["hint_verified"] = bool(hint_state.get("verified", False))
    metrics["hint_expired"] = bool(hint_state.get("expired", False))
    metrics["hint_bundle_kind"] = str(hint_bundle_info.get("kind", "") or "-")
    metrics["hint_effective"] = bool(
        metrics.get("hint_applied", False)
        and (
            float(metrics.get("confidence_delta", 0.0) or 0.0) > 0.0
            or float(metrics.get("hint_score_delta", 0.0) or 0.0) > 0.0
            or bool(metrics.get("hint_verified", False))
        )
    )
    if "confidence_delta" not in metrics:
        metrics["confidence_delta"] = 0.0
    hint_state["effective"] = bool(metrics.get("hint_effective", False))
    hint_state["confidence_delta"] = float(metrics.get("confidence_delta", 0.0) or 0.0)
    scan_io_stats = metrics.get("scan_io_stats", {}) if isinstance(metrics.get("scan_io_stats"), dict) else {}
    scan_graph_payload = metrics.get("scan_graph", {}) if isinstance(metrics.get("scan_graph"), dict) else {}
    scan_graph_io = scan_graph_payload.get("io_stats", {}) if isinstance(scan_graph_payload.get("io_stats"), dict) else {}
    if not scan_io_stats:
        scan_io_stats = {
            "layout_adapter_runs": int(metrics.get("layout_adapter_runs", 1) or 1),
            "java_files_scanned": int(scan_graph_io.get("java_scanned", len(all_java_results)) or 0),
            "templates_scanned": int(scan_graph_io.get("template_scanned", len(all_templates)) or 0),
            "snapshot_files_count": int(len(snap_before)),
            "cache_hit_files": int(metrics.get("cache_hit_files", 0) or 0),
            "cache_miss_files": int(metrics.get("cache_miss_files", 0) or 0),
            "cache_hit_rate": float(metrics.get("cache_hit_rate", 0.0) or 0.0),
            "bytes_read": int(scan_graph_io.get("bytes_read", 0) or 0),
            "scan_graph_used": 1 if scan_graph_payload.get("used") else 0,
            "scan_graph_cache_key": str(scan_graph_payload.get("cache_key", "") or ""),
        }
    else:
        scan_io_stats.setdefault("layout_adapter_runs", int(metrics.get("layout_adapter_runs", 1) or 1))
        scan_io_stats.setdefault("java_files_scanned", int(len(all_java_results)))
        scan_io_stats.setdefault("templates_scanned", int(len(all_templates)))
        scan_io_stats.setdefault("snapshot_files_count", int(len(snap_before)))
        scan_io_stats.setdefault("cache_hit_files", int(metrics.get("cache_hit_files", 0) or 0))
        scan_io_stats.setdefault("cache_miss_files", int(metrics.get("cache_miss_files", 0) or 0))
        scan_io_stats.setdefault("cache_hit_rate", float(metrics.get("cache_hit_rate", 0.0) or 0.0))
        scan_io_stats.setdefault("bytes_read", int(scan_graph_io.get("bytes_read", 0) or 0))
        scan_io_stats.setdefault("scan_graph_used", 1 if scan_graph_payload.get("used") else 0)
        scan_io_stats.setdefault("scan_graph_cache_key", str(scan_graph_payload.get("cache_key", "") or ""))
    metrics["scan_io_stats"] = scan_io_stats
    if not isinstance(metrics.get("scan_graph"), dict):
        metrics["scan_graph"] = {"used": False, "cache_key": "", "cache_hit_rate": 0.0, "java_files_indexed": 0, "bytes_read": 0}
    else:
        metrics["scan_graph"].setdefault("used", False)
        metrics["scan_graph"].setdefault("cache_key", "")
        metrics["scan_graph"].setdefault("cache_hit_rate", float(scan_io_stats.get("cache_hit_rate", 0.0) or 0.0))
        metrics["scan_graph"].setdefault("java_files_indexed", int(scan_io_stats.get("java_files_scanned", 0) or 0))
        metrics["scan_graph"].setdefault("bytes_read", int(scan_io_stats.get("bytes_read", 0) or 0))
    metrics.setdefault("hint_bundle", "-")
    metrics.setdefault("hints_emitted", False)
    metrics.setdefault("module_candidates", len(roots_info))
    metrics.setdefault("ambiguity_ratio", round(float(ambiguity_ratio), 4))
    ensure_endpoints_total(metrics)

    # Snapshot after — enforce read-only contract
    snap_after = take_snapshot(repo_root)
    delta = diff_snapshots(snap_before, snap_after)
    enforce_read_only(delta, args.write_ok)

    limits_hit, limit_codes, limit_texts = evaluate_limits(args, metrics, scan_time)
    metrics["limits_suggestion"] = build_limits_suggestion(limit_codes, "discover", keywords)
    for reason in limit_texts:
        warnings_list.append(f"limits_hit: {reason}")
        print(f"[plugin] WARN: limits_hit: {reason}", file=sys.stderr)
    if metrics.get("limits_suggestion"):
        print(f"[plugin] limits_suggestion: {metrics['limits_suggestion']}", file=sys.stderr)
    if limits_hit and args.strict and final_exit_code == 0:
        final_exit_code = LIMIT_EXIT_CODE
        print("[plugin] STRICT: limits hit, exiting with code 20", file=sys.stderr)

    calibration_report = run_discover_calibration(
        workspace=ws,
        candidates=discover_candidates,
        metrics=metrics,
        roots_info=roots_info,
        structure_signals=structure_signals,
        keywords=keywords,
        min_confidence=float(args.min_confidence),
        ambiguity_threshold=float(args.ambiguity_threshold),
        emit_hints=bool(args.emit_hints),
    )
    metrics["needs_human_hint"] = bool(calibration_report.get("needs_human_hint", False))
    metrics["confidence_tier"] = str(calibration_report.get("confidence_tier", "low"))
    metrics["calibration_confidence"] = float(calibration_report.get("confidence", 0.0) or 0.0)
    metrics.setdefault("exit_hint", "-")
    for action in calibration_report.get("action_suggestions", []):
        if action not in suggestions_list:
            suggestions_list.append(action)
    if metrics["needs_human_hint"]:
        reason_text = ",".join(calibration_report.get("reasons", [])) or "needs_human_hint"
        warn = f"needs_human_hint: {reason_text}"
        warnings_list.append(warn)
        print(f"[plugin] WARN: {warn}", file=sys.stderr)
        if args.strict and final_exit_code == 0:
            final_exit_code = CALIBRATION_EXIT_CODE
            metrics["exit_hint"] = "needs_human_hint"
            print("[plugin] STRICT: needs_human_hint detected, exiting with code 21", file=sys.stderr)

    if scan_graph_mismatch_detected:
        metrics["mismatch_reason"] = normalize_mismatch_reason(scan_graph_mismatch_reason or "unknown")
        metrics["mismatch_detail"] = str(scan_graph_mismatch_detail or "scan_graph_mismatch")
        metrics["mismatch_suggestion"] = mismatch_suggestion_for(metrics["mismatch_reason"])

    if scan_graph_mismatch_detected and args.strict and final_exit_code == 0:
        final_exit_code = SCAN_GRAPH_MISMATCH_EXIT_CODE
        metrics["exit_hint"] = "scan_graph_mismatch"
        if scan_graph_mismatch_detail and str(scan_graph_mismatch_detail) != "-":
            warnings_list.append(f"scan_graph_mismatch_detail: {scan_graph_mismatch_detail}")
        print("[plugin] STRICT: scan_graph mismatch detected, exiting with code 25", file=sys.stderr)
    else:
        metrics.setdefault("mismatch_reason", "-")
        metrics.setdefault("mismatch_detail", "-")
        metrics.setdefault("mismatch_suggestion", "-")

    gov_info = getattr(args, "_gov_info", {})
    hint_scope_allowed, hint_scope_reason = hint_bundle_scope_allowed(gov_info)
    if hint_state.get("applied") and hint_bundle_info.get("path"):
        metrics["hint_bundle"] = str(hint_bundle_info.get("path"))
    should_emit_hint_bundle = bool(metrics.get("needs_human_hint", False)) and not (
        final_exit_code == HINT_VERIFY_EXIT_CODE and bool(hint_state.get("expired", False))
    )
    if should_emit_hint_bundle:
        if hint_scope_allowed:
            hint_state["layout_hints"] = {
                "layout": str(layout),
                "adapter_used": str(layout_details.get("adapter_used", "")),
            }
            roots_backend: List[str] = []
            roots_templates: List[str] = []
            for entry in roots_info:
                if not isinstance(entry, dict):
                    continue
                for root_item in entry.get("roots", []) if isinstance(entry.get("roots"), list) else []:
                    if not isinstance(root_item, dict):
                        continue
                    kind = str(root_item.get("kind", "") or "")
                    path = str(root_item.get("path", "") or "")
                    if not path:
                        continue
                    if kind == "backend_java" and path not in roots_backend:
                        roots_backend.append(path)
                    if kind == "web_template" and path not in roots_templates:
                        roots_templates.append(path)
            hint_state["roots_hints"] = {"backend_java": roots_backend, "web_template": roots_templates}
            hint_bundle_path = emit_hint_bundle(
                workspace=ws,
                command="discover",
                repo_fingerprint=fp,
                run_id=run_id,
                calibration_report=calibration_report,
                hint_state=hint_state,
                hint_bundle_info=hint_bundle_info,
                emit_hints=bool(args.emit_hints),
                ttl_seconds=int(getattr(args, "hint_bundle_ttl_seconds", 1800)),
            )
            if hint_bundle_path:
                hint_state["emitted"] = True
                hint_state["bundle_path"] = hint_bundle_path
                hint_state["kind"] = str(hint_bundle_info.get("kind", HINT_BUNDLE_KIND_PROFILE_DELTA))
                hint_state["verified"] = True
                hint_state["expired"] = False
                hint_state["ttl_seconds"] = int(hint_bundle_info.get("ttl_seconds", 0) or 0)
                hint_state["created_at"] = str(hint_bundle_info.get("created_at", "") or "")
                hint_state["expires_at"] = str(hint_bundle_info.get("expires_at", "") or "")
                metrics["hint_bundle"] = hint_bundle_path
                metrics["hints_emitted"] = True
        else:
            warnings_list.append(f"hint_bundle_blocked: {hint_scope_reason}")
            print(f"[plugin] WARN: hint bundle blocked: {hint_scope_reason}", file=sys.stderr)
            print_hints_block_line(
                code=HINT_SCOPE_EXIT_CODE,
                reason=hint_scope_reason,
                command="discover",
                detail="hint bundle emission blocked by token scope",
                token_scope=normalize_scope(gov_info.get("token_scope")),
            )
            metrics["exit_hint"] = "hint_bundle_scope_missing"
            if args.strict:
                final_exit_code = HINT_SCOPE_EXIT_CODE
    metrics["hint_bundle_kind"] = str(hint_bundle_info.get("kind", "-") or "-")
    metrics["hint_verified"] = bool(hint_bundle_info.get("verified", hint_state.get("verified", False)))
    metrics["hint_expired"] = bool(hint_bundle_info.get("expired", hint_state.get("expired", False)))
    metrics["hint_bundle_expires_at"] = str(hint_bundle_info.get("expires_at", "") or "")
    metrics["hint_bundle_created_at"] = str(hint_bundle_info.get("created_at", "") or "")
    metrics.setdefault("hint_bundle", "-")
    metrics.setdefault("hints_emitted", False)
    metrics["keywords_used"] = keywords[:8]
    metrics["endpoint_paths"] = structure_signals.get("endpoint_paths", [])[:120]

    if final_exit_code == 0:
        capability_registry = update_capability_registry(
            global_state_root,
            fp,
            repo_root,
            "discover",
            run_id,
            ws,
            vcs,
            metrics,
            modules_summary,
            warnings_list,
            suggestions_list,
            smart_info,
            gov_info,
        )
    final_exit_code, federated_registry = maybe_update_federated_registry(
        command="discover",
        args=args,
        final_exit_code=final_exit_code,
        global_state_root=global_state_root,
        repo_root=repo_root,
        fp=fp,
        run_id=run_id,
        ws=ws,
        metrics=metrics,
        layout=layout,
        governance=gov_info,
        capability_registry=capability_registry,
        warnings_list=warnings_list,
    )
    cap_path = write_capabilities(
        workspace=ws,
        command="discover",
        run_id=run_id,
        repo_fingerprint=fp,
        layout=layout,
        roots=roots_info,
        artifacts=artifacts_list,
        metrics=metrics,
        warnings=warnings_list,
        suggestions=suggestions_list,
        governance=gov_info,
        smart=smart_info,
        capability_registry=capability_registry,
        calibration=calibration_report,
        hints=hint_state,
        hint_bundle=hint_bundle_info,
        layout_details=layout_details,
        federated_index=federated_registry,
    )
    print(f"[plugin] capabilities: {cap_path}", file=sys.stderr)
    print(f"[plugin] capability_index: {capability_registry['index_path']}", file=sys.stderr)
    print(f"[plugin] latest_pointer: {capability_registry['latest_path']}", file=sys.stderr)
    if federated_registry.get("updated"):
        print_index_pointer_line(
            Path(str(federated_registry["path"])),
            command="discover",
            repo_fingerprint=fp,
            run_id=run_id,
            mismatch_reason=str(metrics.get("mismatch_reason", "-") or "-"),
            mismatch_detail=str(metrics.get("mismatch_detail", "-") or "-"),
            mismatch_suggestion=str(metrics.get("mismatch_suggestion", "-") or "-"),
        )
    emit_capability_contract_lines(
        cap_path=cap_path,
        command="discover",
        fp=fp,
        run_id=run_id,
        smart_info=smart_info,
        metrics=metrics,
        governance=gov_info,
        workspace=ws,
        exit_code=final_exit_code,
        warnings_count=len(warnings_list),
        layout=layout,
        calibration=calibration_report,
        hints=hint_state,
        hint_bundle=hint_bundle_info,
        federated_index=federated_registry,
        layout_details=layout_details,
    )
    return final_exit_code


# ═══════════════════════════════════════════════════════════════════════════════
#  Subcommand: diff
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_diff(args):
    """Cross-project structure diff."""
    old_root = Path(args.old_project_root).resolve()
    new_root = Path(args.new_project_root).resolve()
    for r, name in [(old_root, "old"), (new_root, "new")]:
        if not r.is_dir():
            print(f"FAIL: {name}-project-root not found: {r}", file=sys.stderr)
            sys.exit(1)

    # Use new_root for fingerprint
    fp = compute_project_fingerprint(new_root)
    run_id = utc_now_run_id()
    ws = resolve_workspace(fp, run_id, args.workspace_root)
    global_state_root = resolve_global_state(args)
    vcs = detect_vcs_info(new_root)
    assert_output_roots_safe(new_root, ws, global_state_root)
    assert_output_roots_safe(old_root, ws, global_state_root)
    diff_dir = ws / "diff"
    diff_dir.mkdir(parents=True, exist_ok=True)

    warnings_list = []
    suggestions_list = []
    artifacts_list = []
    roots_info = []
    modules_summary = {}
    smart_info = {
        "enabled": bool(args.smart),
        "reused": False,
        "reused_from_run_id": None,
        "reuse_validated": False,
    }
    capability_registry = {
        "global_state_root": str(global_state_root),
        "index_path": str(global_state_root / "capability_index.json"),
        "latest_path": "",
        "run_meta_path": "",
        "updated": False,
    }
    federated_registry = {
        "path": str(global_state_root / "federated_index.json"),
        "jsonl_path": str(global_state_root / "federated_index.jsonl"),
        "mirror_path": "",
        "updated": False,
        "blocked_reason": "",
    }
    metrics = {}

    # Snapshot before (both repos)
    snap_old_before = take_snapshot(old_root)
    snap_new_before = take_snapshot(new_root)

    t_start = time.time()
    smart_info, reused_payload, smart_reasons = attempt_smart_reuse(
        "diff", args, new_root, fp, vcs, ws, global_state_root
    )
    for reason in smart_reasons:
        if reason.startswith("WARN:"):
            warnings_list.append(reason[5:].strip())
            print(f"[plugin] WARN: {reason[5:].strip()}", file=sys.stderr)
        elif args.smart and not smart_info.get("reused"):
            print(f"[plugin] smart-skip: {reason}", file=sys.stderr)

    if smart_info.get("reused"):
        metrics = reused_payload.get("metrics", {})
        warnings_list.extend(reused_payload.get("warnings", []))
        suggestions_list.extend(reused_payload.get("suggestions", []))
        artifacts_list = reused_payload.get("artifacts", [])
        ensure_endpoints_total(metrics)
    else:
        sys.path.insert(0, str(SCRIPT_DIR))
        try:
            import cross_project_structure_diff as cpsd
        except ImportError:
            print("FAIL: cross_project_structure_diff.py not found", file=sys.stderr)
            sys.exit(1)

        # Determine module_key from auto-discover if not specified
        module_key = args.module_key
        if not module_key:
            try:
                import auto_module_discover as amd

                java_roots = amd.find_java_roots(new_root)
                all_pkgs = {}
                for jr in java_roots:
                    for pkg, stats in amd.scan_packages(jr).items():
                        if pkg not in all_pkgs:
                            all_pkgs[pkg] = {"files": 0, "controllers": 0, "services": 0, "repositories": 0}
                        for k in ("files", "controllers", "services", "repositories"):
                            all_pkgs[pkg][k] += stats[k]
                keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else []
                cands = amd.cluster_modules(all_pkgs, keywords)[:1]
                module_key = cands[0]["module_key"] if cands else "unknown"
            except Exception:
                module_key = "unknown"
        old_scan_graph_path = str(getattr(args, "old_scan_graph", "") or "").strip()
        new_scan_graph_path = str(getattr(args, "new_scan_graph", "") or "").strip()
        ws_hint = Path(args.workspace_root).resolve() if getattr(args, "workspace_root", None) else None
        if not old_scan_graph_path:
            old_scan_graph_path = find_latest_scan_graph_by_fp(
                global_state_root,
                compute_project_fingerprint(old_root),
                workspace_root_hint=ws_hint,
            )
        if not new_scan_graph_path:
            new_scan_graph_path = find_latest_scan_graph_by_fp(
                global_state_root,
                fp,
                workspace_root_hint=ws_hint,
            )
        old_scan_graph = load_scan_graph_any(old_scan_graph_path) if old_scan_graph_path else {}
        new_scan_graph = load_scan_graph_any(new_scan_graph_path) if new_scan_graph_path else {}

        if old_scan_graph and new_scan_graph:
            old_classes = classes_from_scan_graph(old_scan_graph, module_key)
            new_classes = classes_from_scan_graph(new_scan_graph, module_key)
            old_templates = templates_from_scan_graph(old_scan_graph, module_key)
            new_templates = templates_from_scan_graph(new_scan_graph, module_key)
            old_io = old_scan_graph.get("io_stats", {}) if isinstance(old_scan_graph.get("io_stats"), dict) else {}
            new_io = new_scan_graph.get("io_stats", {}) if isinstance(new_scan_graph.get("io_stats"), dict) else {}
            metrics["scan_graph"] = {
                "used": True,
                "old_path": old_scan_graph_path,
                "new_path": new_scan_graph_path,
                "old_cache_key": str(old_scan_graph.get("cache_key", "") or ""),
                "new_cache_key": str(new_scan_graph.get("cache_key", "") or ""),
                "cache_hit_rate": float(new_io.get("cache_hit_rate", 0.0) or 0.0),
                "java_files_indexed": 0,
                "bytes_read": 0,
                "source_java_files_indexed": int(new_io.get("java_scanned", 0) or 0),
                "source_bytes_read": int(new_io.get("bytes_read", 0) or 0),
                "io_stats": {
                    "old": old_io,
                    "new": new_io,
                },
            }
        else:
            if (old_scan_graph_path and not old_scan_graph) or (new_scan_graph_path and not new_scan_graph):
                warnings_list.append("scan_graph_not_usable_for_diff")
            old_classes = cpsd.scan_classes(old_root, module_key)
            new_classes = cpsd.scan_classes(new_root, module_key)
            old_templates = cpsd.scan_templates(old_root, module_key)
            new_templates = cpsd.scan_templates(new_root, module_key)
            metrics["scan_graph"] = {"used": False}

        diff_result = cpsd.diff_structures(old_classes, new_classes, old_templates, new_templates)
        scan_time = time.time() - t_start

        out_path = diff_dir / f"{module_key}.diff.yaml"
        cpsd.write_diff_report(
            out_path,
            module_key,
            diff_result,
            str(old_root),
            str(new_root),
            scan_time,
            read_only=False,
        )
        artifacts_list.append(str(out_path))
        metrics = {
            **metrics,
            "module_key": module_key,
            "scan_time_s": round(scan_time, 3),
            "missing_classes": len(diff_result.get("missing_classes", [])),
            "new_classes": len(diff_result.get("new_classes", [])),
            "files_scanned": len(old_classes) + len(new_classes) + len(old_templates) + len(new_templates),
        }
        ep_diff = diff_result.get("endpoint_diff", {})
        metrics["endpoints_added"] = len(ep_diff.get("added", []))
        metrics["endpoints_removed"] = len(ep_diff.get("removed", []))
        metrics["endpoints_changed"] = len(ep_diff.get("changed", []))
        metrics["endpoints_total"] = (
            metrics["endpoints_added"] + metrics["endpoints_removed"] + metrics["endpoints_changed"]
        )
        modules_summary[module_key] = {
            "package_prefix": module_key,
            "confidence": 1.0,
            "roots": [],
            "endpoints": metrics["endpoints_total"],
        }

    # Snapshot after — enforce read-only
    snap_old_after = take_snapshot(old_root)
    snap_new_after = take_snapshot(new_root)
    delta_old = diff_snapshots(snap_old_before, snap_old_after)
    delta_new = diff_snapshots(snap_new_before, snap_new_after)
    enforce_read_only(delta_old, args.write_ok)
    enforce_read_only(delta_new, args.write_ok)

    if "scan_time_s" not in metrics:
        metrics["scan_time_s"] = round(time.time() - t_start, 3)
    metrics.setdefault("module_candidates", 1 if metrics.get("module_key") else 0)
    metrics.setdefault("ambiguity_ratio", 0.0)
    metrics.setdefault("confidence_tier", "high")
    metrics.setdefault("keywords_used", [])
    metrics.setdefault("endpoint_paths", [])
    if not isinstance(metrics.get("scan_io_stats"), dict):
        metrics["scan_io_stats"] = {}
    if isinstance(metrics.get("scan_graph"), dict):
        sg = metrics["scan_graph"]
        sg_io = sg.get("io_stats", {}) if isinstance(sg.get("io_stats"), dict) else {}
        new_io = sg_io.get("new", {}) if isinstance(sg_io.get("new"), dict) else {}
        metrics["scan_io_stats"].setdefault("java_files_scanned", 0)
        metrics["scan_io_stats"].setdefault("templates_scanned", 0)
        metrics["scan_io_stats"].setdefault("bytes_read", 0)
        metrics["scan_io_stats"].setdefault("cache_hit_rate", float(new_io.get("cache_hit_rate", 0.0) or 0.0))
        metrics["scan_io_stats"].setdefault("source_java_files_indexed", int(new_io.get("java_scanned", 0) or 0))
        metrics["scan_io_stats"].setdefault("source_templates_indexed", int(new_io.get("template_scanned", 0) or 0))
        metrics["scan_io_stats"].setdefault("source_bytes_read", int(new_io.get("bytes_read", 0) or 0))
        sg.setdefault("cache_hit_rate", float(new_io.get("cache_hit_rate", 0.0) or 0.0))
        sg.setdefault("java_files_indexed", 0)
        sg.setdefault("bytes_read", 0)
        sg.setdefault("source_java_files_indexed", int(new_io.get("java_scanned", 0) or 0))
        sg.setdefault("source_bytes_read", int(new_io.get("bytes_read", 0) or 0))
    ensure_endpoints_total(metrics)
    limits_hit, _limit_codes, limit_texts = evaluate_limits(args, metrics, float(metrics["scan_time_s"]))
    metrics["limits_suggestion"] = build_limits_suggestion(_limit_codes, "diff", [])
    for reason in limit_texts:
        warnings_list.append(f"limits_hit: {reason}")
        print(f"[plugin] WARN: limits_hit: {reason}", file=sys.stderr)
    if metrics.get("limits_suggestion"):
        print(f"[plugin] limits_suggestion: {metrics['limits_suggestion']}", file=sys.stderr)
    final_exit_code = 0
    if limits_hit and args.strict:
        final_exit_code = LIMIT_EXIT_CODE
        print("[plugin] STRICT: limits hit, exiting with code 20", file=sys.stderr)

    gov_info = getattr(args, "_gov_info", {})
    if final_exit_code == 0:
        capability_registry = update_capability_registry(
            global_state_root,
            fp,
            new_root,
            "diff",
            run_id,
            ws,
            vcs,
            metrics,
            modules_summary,
            warnings_list,
            suggestions_list,
            smart_info,
            gov_info,
        )
    final_exit_code, federated_registry = maybe_update_federated_registry(
        command="diff",
        args=args,
        final_exit_code=final_exit_code,
        global_state_root=global_state_root,
        repo_root=new_root,
        fp=fp,
        run_id=run_id,
        ws=ws,
        metrics=metrics,
        layout="n/a",
        governance=gov_info,
        capability_registry=capability_registry,
        warnings_list=warnings_list,
    )
    cap_path = write_capabilities(
        workspace=ws,
        command="diff",
        run_id=run_id,
        repo_fingerprint=fp,
        layout="n/a",
        roots=roots_info,
        artifacts=artifacts_list,
        metrics=metrics,
        warnings=warnings_list,
        suggestions=suggestions_list,
        governance=gov_info,
        smart=smart_info,
        capability_registry=capability_registry,
        federated_index=federated_registry,
    )
    print(f"[plugin] capabilities: {cap_path}", file=sys.stderr)
    print(f"[plugin] capability_index: {capability_registry['index_path']}", file=sys.stderr)
    print(f"[plugin] latest_pointer: {capability_registry['latest_path']}", file=sys.stderr)
    if federated_registry.get("updated"):
        print_index_pointer_line(
            Path(str(federated_registry["path"])),
            command="diff",
            repo_fingerprint=fp,
            run_id=run_id,
            mismatch_reason=str(metrics.get("mismatch_reason", "-") or "-"),
            mismatch_detail=str(metrics.get("mismatch_detail", "-") or "-"),
            mismatch_suggestion=str(metrics.get("mismatch_suggestion", "-") or "-"),
        )
    emit_capability_contract_lines(
        cap_path=cap_path,
        command="diff",
        fp=fp,
        run_id=run_id,
        smart_info=smart_info,
        metrics=metrics,
        governance=gov_info,
        workspace=ws,
        exit_code=final_exit_code,
        warnings_count=len(warnings_list),
        layout="n/a",
        federated_index=federated_registry,
    )
    return final_exit_code


# ═══════════════════════════════════════════════════════════════════════════════
#  Subcommand: profile
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_profile(args):
    """Generate effective profile into workspace."""
    repo_root = Path(args.repo_root).resolve()
    fp = compute_project_fingerprint(repo_root)
    run_id = utc_now_run_id()
    ws = resolve_workspace(fp, run_id, args.workspace_root)
    global_state_root = resolve_global_state(args)
    vcs = detect_vcs_info(repo_root)
    assert_output_roots_safe(repo_root, ws, global_state_root)
    prof_dir = ws / "profile"
    prof_dir.mkdir(parents=True, exist_ok=True)

    warnings_list = []
    suggestions_list = []
    artifacts_list = []
    metrics = {}
    modules_summary = {}
    roots_info = []
    smart_info = {
        "enabled": bool(args.smart),
        "reused": False,
        "reused_from_run_id": None,
        "reuse_validated": False,
    }
    capability_registry = {
        "global_state_root": str(global_state_root),
        "index_path": str(global_state_root / "capability_index.json"),
        "latest_path": "",
        "run_meta_path": "",
        "updated": False,
    }
    federated_registry = {
        "path": str(global_state_root / "federated_index.json"),
        "jsonl_path": str(global_state_root / "federated_index.jsonl"),
        "mirror_path": "",
        "updated": False,
        "blocked_reason": "",
    }

    snap_before = take_snapshot(repo_root)
    t_start = time.time()

    smart_info, reused_payload, smart_reasons = attempt_smart_reuse(
        "profile", args, repo_root, fp, vcs, ws, global_state_root
    )
    for reason in smart_reasons:
        if reason.startswith("WARN:"):
            warnings_list.append(reason[5:].strip())
            print(f"[plugin] WARN: {reason[5:].strip()}", file=sys.stderr)
        elif args.smart and not smart_info.get("reused"):
            print(f"[plugin] smart-skip: {reason}", file=sys.stderr)

    module_key = args.module_key
    if smart_info.get("reused"):
        metrics = reused_payload.get("metrics", {})
        warnings_list.extend(reused_payload.get("warnings", []))
        suggestions_list.extend(reused_payload.get("suggestions", []))
        artifacts_list = reused_payload.get("artifacts", [])
        ensure_endpoints_total(metrics)
    else:
        sys.path.insert(0, str(SCRIPT_DIR))
        scan_graph_payload = {}
        scan_graph_path = str(getattr(args, "scan_graph", "") or "").strip()
        if not scan_graph_path:
            ws_hint = Path(args.workspace_root).resolve() if getattr(args, "workspace_root", None) else None
            scan_graph_path = find_latest_scan_graph_by_fp(
                global_state_root,
                fp,
                workspace_root_hint=ws_hint,
            )
        if scan_graph_path:
            scan_graph_payload = load_scan_graph_any(scan_graph_path)
            if not scan_graph_payload:
                warnings_list.append(f"scan_graph_not_usable: {scan_graph_path}")

        # Auto-discover if no module_key
        if not module_key:
            try:
                import auto_module_discover as amd

                java_roots = amd.find_java_roots(repo_root)
                all_pkgs = {}
                for jr in java_roots:
                    for pkg, stats in amd.scan_packages(jr).items():
                        if pkg not in all_pkgs:
                            all_pkgs[pkg] = {"files": 0, "controllers": 0, "services": 0, "repositories": 0}
                        for k in ("files", "controllers", "services", "repositories"):
                            all_pkgs[pkg][k] += stats[k]
                keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else []
                cands = amd.cluster_modules(all_pkgs, keywords)[:1]
                module_key = cands[0]["module_key"] if cands else None
            except Exception:
                module_key = None

        if not module_key:
            warnings_list.append("no module candidates found for profile generation")
            print("[plugin] WARN: no module candidates found", file=sys.stderr)
        else:
            print(f"[plugin] generating profile for module: {module_key}", file=sys.stderr)
            prof_file = prof_dir / f"{module_key}.profile.yaml"
            if scan_graph_payload:
                write_profile_from_scan_graph(prof_file, module_key, scan_graph_payload)
                io_stats = scan_graph_payload.get("io_stats", {}) if isinstance(scan_graph_payload.get("io_stats"), dict) else {}
                metrics["scan_graph"] = {
                    "used": True,
                    "path": scan_graph_path,
                    "cache_key": str(scan_graph_payload.get("cache_key", "") or ""),
                    "cache_hit_rate": float(io_stats.get("cache_hit_rate", 0.0) or 0.0),
                    "java_files_indexed": 0,
                    "bytes_read": 0,
                    "source_java_files_indexed": int(io_stats.get("java_scanned", 0) or 0),
                    "source_bytes_read": int(io_stats.get("bytes_read", 0) or 0),
                    "io_stats": io_stats,
                }
                metrics["scan_io_stats"] = {
                    "java_files_scanned": 0,
                    "templates_scanned": 0,
                    "bytes_read": 0,
                    "cache_hit_rate": float(io_stats.get("cache_hit_rate", 0.0) or 0.0),
                    "scan_graph_used": 1,
                    "source_java_files_indexed": int(io_stats.get("java_scanned", 0) or 0),
                    "source_templates_indexed": int(io_stats.get("template_scanned", 0) or 0),
                    "source_bytes_read": int(io_stats.get("bytes_read", 0) or 0),
                }
                metrics["files_scanned"] = int(io_stats.get("files_indexed", 0) or 0)
            else:
                # Keep backward-compatible fallback when scan graph is unavailable.
                prof_file.write_text(f"# Profile for {module_key}\n", encoding="utf-8")
                metrics["scan_graph"] = {"used": False}
            artifacts_list.append(str(prof_file))

        scan_time = time.time() - t_start
        metrics = {
            **metrics,
            "module_key": module_key or "none",
            "scan_time_s": round(scan_time, 3),
            "endpoints_total": int(metrics.get("endpoints_total", 0) or 0),
        }
        if module_key:
            modules_summary[module_key] = {
                "package_prefix": module_key,
                "confidence": 1.0,
                "roots": [],
                "endpoints": int(metrics.get("endpoints_total", 0) or 0),
            }

    snap_after = take_snapshot(repo_root)
    delta = diff_snapshots(snap_before, snap_after)
    enforce_read_only(delta, args.write_ok)

    if "scan_time_s" not in metrics:
        metrics["scan_time_s"] = round(time.time() - t_start, 3)
    keywords_used = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else []
    metrics.setdefault("module_candidates", 1 if metrics.get("module_key") and metrics.get("module_key") != "none" else 0)
    metrics.setdefault("ambiguity_ratio", 0.0)
    metrics.setdefault("confidence_tier", "high")
    metrics.setdefault("keywords_used", keywords_used)
    metrics.setdefault("endpoint_paths", [])
    if not isinstance(metrics.get("scan_graph"), dict):
        metrics["scan_graph"] = {"used": False}
    if not isinstance(metrics.get("scan_io_stats"), dict):
        metrics["scan_io_stats"] = {}
    if isinstance(metrics.get("scan_graph"), dict):
        sg = metrics["scan_graph"]
        sg_io = sg.get("io_stats", {}) if isinstance(sg.get("io_stats"), dict) else {}
        metrics["scan_io_stats"].setdefault("java_files_scanned", int(sg_io.get("java_scanned", 0) or 0))
        metrics["scan_io_stats"].setdefault("templates_scanned", int(sg_io.get("template_scanned", 0) or 0))
        metrics["scan_io_stats"].setdefault("bytes_read", int(sg_io.get("bytes_read", 0) or 0))
        metrics["scan_io_stats"].setdefault("cache_hit_rate", float(sg_io.get("cache_hit_rate", 0.0) or 0.0))
        sg.setdefault("cache_hit_rate", float(sg_io.get("cache_hit_rate", 0.0) or 0.0))
        sg.setdefault("java_files_indexed", int(sg_io.get("java_scanned", 0) or 0))
        sg.setdefault("bytes_read", int(sg_io.get("bytes_read", 0) or 0))
    ensure_endpoints_total(metrics)
    limits_hit, _limit_codes, limit_texts = evaluate_limits(args, metrics, float(metrics["scan_time_s"]))
    metrics["limits_suggestion"] = build_limits_suggestion(_limit_codes, "profile", keywords_used)
    for reason in limit_texts:
        warnings_list.append(f"limits_hit: {reason}")
        print(f"[plugin] WARN: limits_hit: {reason}", file=sys.stderr)
    if metrics.get("limits_suggestion"):
        print(f"[plugin] limits_suggestion: {metrics['limits_suggestion']}", file=sys.stderr)
    final_exit_code = 0
    if limits_hit and args.strict:
        final_exit_code = LIMIT_EXIT_CODE
        print("[plugin] STRICT: limits hit, exiting with code 20", file=sys.stderr)
    gov_info = getattr(args, "_gov_info", {})
    if final_exit_code == 0:
        capability_registry = update_capability_registry(
            global_state_root,
            fp,
            repo_root,
            "profile",
            run_id,
            ws,
            vcs,
            metrics,
            modules_summary,
            warnings_list,
            suggestions_list,
            smart_info,
            gov_info,
        )
    layout = detect_layout(repo_root)
    final_exit_code, federated_registry = maybe_update_federated_registry(
        command="profile",
        args=args,
        final_exit_code=final_exit_code,
        global_state_root=global_state_root,
        repo_root=repo_root,
        fp=fp,
        run_id=run_id,
        ws=ws,
        metrics=metrics,
        layout=layout,
        governance=gov_info,
        capability_registry=capability_registry,
        warnings_list=warnings_list,
    )
    cap_path = write_capabilities(
        workspace=ws,
        command="profile",
        run_id=run_id,
        repo_fingerprint=fp,
        layout=layout,
        roots=roots_info,
        artifacts=artifacts_list,
        metrics=metrics,
        warnings=warnings_list,
        suggestions=suggestions_list,
        governance=gov_info,
        smart=smart_info,
        capability_registry=capability_registry,
        federated_index=federated_registry,
    )
    print(f"[plugin] capabilities: {cap_path}", file=sys.stderr)
    print(f"[plugin] capability_index: {capability_registry['index_path']}", file=sys.stderr)
    print(f"[plugin] latest_pointer: {capability_registry['latest_path']}", file=sys.stderr)
    if federated_registry.get("updated"):
        print_index_pointer_line(
            Path(str(federated_registry["path"])),
            command="profile",
            repo_fingerprint=fp,
            run_id=run_id,
            mismatch_reason=str(metrics.get("mismatch_reason", "-") or "-"),
            mismatch_detail=str(metrics.get("mismatch_detail", "-") or "-"),
            mismatch_suggestion=str(metrics.get("mismatch_suggestion", "-") or "-"),
        )
    emit_capability_contract_lines(
        cap_path=cap_path,
        command="profile",
        fp=fp,
        run_id=run_id,
        smart_info=smart_info,
        metrics=metrics,
        governance=gov_info,
        workspace=ws,
        exit_code=final_exit_code,
        warnings_count=len(warnings_list),
        layout=layout,
        federated_index=federated_registry,
    )
    return final_exit_code


# ═══════════════════════════════════════════════════════════════════════════════
#  Subcommand: migrate
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_migrate(args):
    """Pipeline dry-run (read-only w.r.t. target project)."""
    repo_root = Path(args.repo_root).resolve()
    kit_root = Path(args.kit_root).resolve() if args.kit_root else SCRIPT_DIR.parent.parent

    fp = compute_project_fingerprint(repo_root)
    run_id = utc_now_run_id()
    ws = resolve_workspace(fp, run_id, args.workspace_root)
    global_state_root = resolve_global_state(args)
    vcs = detect_vcs_info(repo_root)
    assert_output_roots_safe(repo_root, ws, global_state_root)
    mig_dir = ws / "migrate"
    mig_dir.mkdir(parents=True, exist_ok=True)

    warnings_list = []
    suggestions_list = []
    artifacts_list = []
    metrics = {}
    modules_summary = {}
    roots_info = []
    smart_info = {
        "enabled": bool(args.smart),
        "reused": False,
        "reused_from_run_id": None,
        "reuse_validated": False,
    }
    capability_registry = {
        "global_state_root": str(global_state_root),
        "index_path": str(global_state_root / "capability_index.json"),
        "latest_path": "",
        "run_meta_path": "",
        "updated": False,
    }
    federated_registry = {
        "path": str(global_state_root / "federated_index.json"),
        "jsonl_path": str(global_state_root / "federated_index.jsonl"),
        "mirror_path": "",
        "updated": False,
        "blocked_reason": "",
    }

    snap_before = take_snapshot(repo_root)
    t_start = time.time()

    smart_info, reused_payload, smart_reasons = attempt_smart_reuse(
        "migrate", args, repo_root, fp, vcs, ws, global_state_root
    )
    for reason in smart_reasons:
        if reason.startswith("WARN:"):
            warnings_list.append(reason[5:].strip())
            print(f"[plugin] WARN: {reason[5:].strip()}", file=sys.stderr)
        elif args.smart and not smart_info.get("reused"):
            print(f"[plugin] smart-skip: {reason}", file=sys.stderr)

    if smart_info.get("reused"):
        metrics = reused_payload.get("metrics", {})
        warnings_list.extend(reused_payload.get("warnings", []))
        suggestions_list.extend(reused_payload.get("suggestions", []))
        artifacts_list = reused_payload.get("artifacts", [])
        ensure_endpoints_total(metrics)
    else:
        # Check if pipeline exists in kit-root
        pipeline_runner = kit_root / "prompt-dsl-system" / "tools" / "pipeline_runner.py"
        if not pipeline_runner.exists():
            warnings_list.append(f"pipeline_runner.py not found at {pipeline_runner}")
            print(f"[plugin] WARN: pipeline_runner.py not found in kit-root: {kit_root}", file=sys.stderr)
        else:
            print(f"[plugin] pipeline dry-run from kit: {kit_root}", file=sys.stderr)
            # In a real implementation, would call pipeline_runner in dry-run mode
            intent = {
                "action": "migrate_dry_run",
                "kit_root": str(kit_root),
                "repo_root": str(repo_root),
                "status": "not_implemented_yet",
            }
            intent_path = mig_dir / "migrate_intent.json"
            intent_path.write_text(json.dumps(intent, indent=2) + "\n", encoding="utf-8")
            artifacts_list.append(str(intent_path))

        scan_time = time.time() - t_start
        metrics = {"scan_time_s": round(scan_time, 3), "endpoints_total": 0}

    snap_after = take_snapshot(repo_root)
    delta = diff_snapshots(snap_before, snap_after)
    enforce_read_only(delta, args.write_ok)

    if "scan_time_s" not in metrics:
        metrics["scan_time_s"] = round(time.time() - t_start, 3)
    metrics.setdefault("module_candidates", 0)
    metrics.setdefault("ambiguity_ratio", 0.0)
    metrics.setdefault("confidence_tier", "high")
    metrics.setdefault("keywords_used", [])
    metrics.setdefault("endpoint_paths", [])
    ensure_endpoints_total(metrics)
    limits_hit, _limit_codes, limit_texts = evaluate_limits(args, metrics, float(metrics["scan_time_s"]))
    metrics["limits_suggestion"] = build_limits_suggestion(_limit_codes, "migrate", [])
    for reason in limit_texts:
        warnings_list.append(f"limits_hit: {reason}")
        print(f"[plugin] WARN: limits_hit: {reason}", file=sys.stderr)
    if metrics.get("limits_suggestion"):
        print(f"[plugin] limits_suggestion: {metrics['limits_suggestion']}", file=sys.stderr)
    final_exit_code = 0
    if limits_hit and args.strict:
        final_exit_code = LIMIT_EXIT_CODE
        print("[plugin] STRICT: limits hit, exiting with code 20", file=sys.stderr)
    gov_info = getattr(args, "_gov_info", {})
    if final_exit_code == 0:
        capability_registry = update_capability_registry(
            global_state_root,
            fp,
            repo_root,
            "migrate",
            run_id,
            ws,
            vcs,
            metrics,
            modules_summary,
            warnings_list,
            suggestions_list,
            smart_info,
            gov_info,
        )
    layout = detect_layout(repo_root)
    final_exit_code, federated_registry = maybe_update_federated_registry(
        command="migrate",
        args=args,
        final_exit_code=final_exit_code,
        global_state_root=global_state_root,
        repo_root=repo_root,
        fp=fp,
        run_id=run_id,
        ws=ws,
        metrics=metrics,
        layout=layout,
        governance=gov_info,
        capability_registry=capability_registry,
        warnings_list=warnings_list,
    )
    cap_path = write_capabilities(
        workspace=ws,
        command="migrate",
        run_id=run_id,
        repo_fingerprint=fp,
        layout=layout,
        roots=roots_info,
        artifacts=artifacts_list,
        metrics=metrics,
        warnings=warnings_list,
        suggestions=suggestions_list,
        governance=gov_info,
        smart=smart_info,
        capability_registry=capability_registry,
        federated_index=federated_registry,
    )
    print(f"[plugin] capabilities: {cap_path}", file=sys.stderr)
    print(f"[plugin] capability_index: {capability_registry['index_path']}", file=sys.stderr)
    print(f"[plugin] latest_pointer: {capability_registry['latest_path']}", file=sys.stderr)
    if federated_registry.get("updated"):
        print_index_pointer_line(
            Path(str(federated_registry["path"])),
            command="migrate",
            repo_fingerprint=fp,
            run_id=run_id,
            mismatch_reason=str(metrics.get("mismatch_reason", "-") or "-"),
            mismatch_detail=str(metrics.get("mismatch_detail", "-") or "-"),
            mismatch_suggestion=str(metrics.get("mismatch_suggestion", "-") or "-"),
        )
    emit_capability_contract_lines(
        cap_path=cap_path,
        command="migrate",
        fp=fp,
        run_id=run_id,
        smart_info=smart_info,
        metrics=metrics,
        governance=gov_info,
        workspace=ws,
        exit_code=final_exit_code,
        warnings_count=len(warnings_list),
        layout=layout,
        federated_index=federated_registry,
    )
    return final_exit_code


# ═══════════════════════════════════════════════════════════════════════════════
#  Subcommand: index
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_index(args):
    """Federated capability index operations: list/query/explain."""
    global_state_root = resolve_global_state(args, read_only=True)
    fed_path = global_state_root / "federated_index.json"
    fed = load_federated_index(fed_path)
    repos = fed.get("repos", {}) if isinstance(fed.get("repos"), dict) else {}
    subcmd = getattr(args, "index_command", None)
    print(f"[plugin] federated_index: {fed_path}")
    print(f"[plugin] federated_index_repos: {len(repos)}")
    print_index_pointer_line(
        fed_path,
        command=f"index:{subcmd or 'list'}",
        repo_fingerprint="-",
        run_id="-",
    )
    if subcmd == "list":
        top_k = max(1, int(getattr(args, "top_k", 20) or 20))
        rows = []
        for fp, entry in repos.items():
            if not isinstance(entry, dict):
                continue
            latest = entry.get("latest", {}) if isinstance(entry.get("latest"), dict) else {}
            runs = entry.get("runs", []) if isinstance(entry.get("runs"), list) else []
            rows.append(
                {
                    "repo_fp": fp,
                    "repo_root": entry.get("repo_root", ""),
                    "last_seen_at": entry.get("last_seen_at", ""),
                    "latest_run_id": latest.get("run_id", ""),
                    "latest_command": latest.get("command", ""),
                    "runs": len(runs),
                }
            )
        rows.sort(key=lambda x: str(x.get("last_seen_at", "")), reverse=True)
        for row in rows[:top_k]:
            print(
                f"repo_fp={row['repo_fp']} runs={row['runs']} "
                f"latest_run_id={row['latest_run_id']} latest_command={row['latest_command']} "
                f"last_seen_at={row['last_seen_at']} repo_root={row['repo_root']}"
            )
        return 0

    if subcmd == "query":
        results = rank_query_runs(
            index=fed,
            keyword=getattr(args, "keyword", ""),
            endpoint=getattr(args, "endpoint", ""),
            top_k=max(1, int(getattr(args, "top_k", 10) or 10)),
            strict_query=bool(getattr(args, "strict", False)),
            include_limits_hit=bool(getattr(args, "include_limits_hit", False)),
        )
        for item in results:
            run = item.get("run", {}) if isinstance(item.get("run"), dict) else {}
            metrics = run.get("metrics", {}) if isinstance(run.get("metrics"), dict) else {}
            print(
                f"repo_fp={item.get('repo_fp','')} run_id={run.get('run_id','')} "
                f"command={run.get('command','')} timestamp={run.get('timestamp','')} "
                f"endpoint_match={item.get('score',[0,0,0,0,0])[0]} "
                f"keyword_match={item.get('score',[0,0,0,0,0])[1]} "
                f"ambiguity_ratio={metrics.get('ambiguity_ratio', 1.0)} "
                f"confidence_tier={metrics.get('confidence_tier','')} "
                f"limits_hit={1 if metrics.get('limits_hit') else 0}"
            )
        return 0

    if subcmd == "explain":
        repo_fp = str(getattr(args, "repo_fp", "") or "").strip()
        run_id = str(getattr(args, "run_id", "") or "").strip()
        entry = repos.get(repo_fp, {}) if isinstance(repos, dict) else {}
        if not isinstance(entry, dict):
            print(f"FAIL: repo_fp not found: {repo_fp}", file=sys.stderr)
            return 1
        runs = entry.get("runs", []) if isinstance(entry.get("runs"), list) else []
        target = None
        for run in runs:
            if isinstance(run, dict) and str(run.get("run_id", "")) == run_id:
                target = run
                break
        if target is None:
            print(f"FAIL: run_id not found under repo_fp={repo_fp}: {run_id}", file=sys.stderr)
            return 1
        print(json.dumps({"repo_fp": repo_fp, "entry": entry, "run": target}, indent=2, ensure_ascii=False))
        return 0

    print("FAIL: missing index subcommand (use: index list|query|explain)", file=sys.stderr)
    return 1


# ═══════════════════════════════════════════════════════════════════════════════
#  Subcommand: scan-graph
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_scan_graph(args):
    repo_root = Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        print(f"FAIL: repo-root not found: {repo_root}", file=sys.stderr)
        return 1

    fp = compute_project_fingerprint(repo_root)
    run_id = utc_now_run_id()
    ws = resolve_workspace(fp, run_id, args.workspace_root)
    global_state_root = resolve_global_state(args)
    vcs = detect_vcs_info(repo_root)
    assert_output_roots_safe(repo_root, ws, global_state_root)
    sg_dir = ws / "scan_graph"
    sg_dir.mkdir(parents=True, exist_ok=True)

    warnings_list: List[str] = []
    suggestions_list: List[str] = []
    artifacts_list: List[str] = []
    roots_info: List[dict] = []
    modules_summary: Dict[str, dict] = {}
    smart_info = {
        "enabled": False,
        "reused": False,
        "reused_from_run_id": None,
        "reuse_validated": False,
    }
    capability_registry = {
        "global_state_root": str(global_state_root),
        "index_path": str(global_state_root / "capability_index.json"),
        "latest_path": "",
        "run_meta_path": "",
        "updated": False,
    }
    federated_registry = {
        "path": str(global_state_root / "federated_index.json"),
        "jsonl_path": str(global_state_root / "federated_index.jsonl"),
        "mirror_path": "",
        "updated": False,
        "blocked_reason": "",
    }
    metrics: Dict[str, Any] = {}

    snap_before = take_snapshot(repo_root)
    t_start = time.time()
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if getattr(args, "keywords", "") else []
    adapter = run_layout_adapters(
        repo_root=repo_root,
        candidates=[],
        keywords=keywords,
        hint_identity={},
        fallback_layout=detect_layout(repo_root),
    )
    java_roots = [Path(p) for p in adapter.get("java_roots", []) if Path(p).is_dir()]
    tpl_roots = [Path(p) for p in adapter.get("template_roots", []) if Path(p).is_dir()]
    roots_for_graph = resolve_scan_graph_roots(repo_root, java_roots, tpl_roots)

    payload = build_scan_graph(
        repo_root=repo_root,
        roots=roots_for_graph,
        max_files=args.max_files,
        max_seconds=args.max_seconds,
        keywords=keywords,
        cache_dir=ws / "scan_cache",
        producer_versions=version_triplet(),
    )
    scan_graph_path = sg_dir / "scan_graph.json"
    save_scan_graph(scan_graph_path, payload)
    artifacts_list.append(str(scan_graph_path))

    io_stats = payload.get("io_stats", {}) if isinstance(payload.get("io_stats"), dict) else {}
    endpoints_total = 0
    for hint in payload.get("java_hints", []) if isinstance(payload.get("java_hints"), list) else []:
        if isinstance(hint, dict):
            endpoints_total += len(hint.get("endpoint_signatures", []) if isinstance(hint.get("endpoint_signatures", []), list) else [])
    metrics = {
        "scan_time_s": round(time.time() - t_start, 3),
        "module_candidates": 0,
        "ambiguity_ratio": 0.0,
        "confidence_tier": "high",
        "keywords_used": keywords[:8],
        "endpoint_paths": [],
        "endpoints_total": int(endpoints_total),
        "scan_graph": {
            "used": True,
            "path": str(scan_graph_path),
            "cache_key": str(payload.get("cache_key", "") or ""),
            "cache_hit_rate": float(io_stats.get("cache_hit_rate", 0.0) or 0.0),
            "java_files_indexed": int(io_stats.get("java_scanned", 0) or 0),
            "bytes_read": int(io_stats.get("bytes_read", 0) or 0),
            "io_stats": io_stats,
        },
        "scan_io_stats": {
            "java_files_scanned": int(io_stats.get("java_scanned", 0) or 0),
            "templates_scanned": int(io_stats.get("template_scanned", 0) or 0),
            "bytes_read": int(io_stats.get("bytes_read", 0) or 0),
            "cache_hit_rate": float(io_stats.get("cache_hit_rate", 0.0) or 0.0),
            "scan_graph_used": 1,
            "scan_graph_cache_key": str(payload.get("cache_key", "") or ""),
        },
        "layout_details": adapter.get("layout_details", {}) if isinstance(adapter.get("layout_details"), dict) else {},
        "files_scanned": int(io_stats.get("files_indexed", 0) or 0),
    }
    if bool(payload.get("limits_hit", False)):
        lr = str(payload.get("limits_reason", "") or "")
        if lr == "max_files" and args.max_files is not None:
            metrics["files_scanned"] = int(args.max_files) + 1

    snap_after = take_snapshot(repo_root)
    delta = diff_snapshots(snap_before, snap_after)
    enforce_read_only(delta, args.write_ok)

    limits_hit, limit_codes, limit_texts = evaluate_limits(args, metrics, float(metrics["scan_time_s"]))
    metrics["limits_suggestion"] = build_limits_suggestion(limit_codes, "scan-graph", keywords)
    for reason in limit_texts:
        warnings_list.append(f"limits_hit: {reason}")
    final_exit_code = 0
    if limits_hit and args.strict:
        final_exit_code = LIMIT_EXIT_CODE
        metrics["exit_hint"] = "limits_hit"

    gov_info = getattr(args, "_gov_info", {})
    if final_exit_code == 0:
        capability_registry = update_capability_registry(
            global_state_root,
            fp,
            repo_root,
            "scan-graph",
            run_id,
            ws,
            vcs,
            metrics,
            modules_summary,
            warnings_list,
            suggestions_list,
            smart_info,
            gov_info,
        )
    layout = str(adapter.get("layout", detect_layout(repo_root)))
    final_exit_code, federated_registry = maybe_update_federated_registry(
        command="scan-graph",
        args=args,
        final_exit_code=final_exit_code,
        global_state_root=global_state_root,
        repo_root=repo_root,
        fp=fp,
        run_id=run_id,
        ws=ws,
        metrics=metrics,
        layout=layout,
        governance=gov_info,
        capability_registry=capability_registry,
        warnings_list=warnings_list,
    )

    cap_path = write_capabilities(
        workspace=ws,
        command="scan-graph",
        run_id=run_id,
        repo_fingerprint=fp,
        layout=layout,
        roots=roots_info,
        artifacts=artifacts_list,
        metrics=metrics,
        warnings=warnings_list,
        suggestions=suggestions_list,
        governance=gov_info,
        smart=smart_info,
        capability_registry=capability_registry,
        federated_index=federated_registry,
    )
    emit_capability_contract_lines(
        cap_path=cap_path,
        command="scan-graph",
        fp=fp,
        run_id=run_id,
        smart_info=smart_info,
        metrics=metrics,
        governance=gov_info,
        workspace=ws,
        exit_code=final_exit_code,
        warnings_count=len(warnings_list),
        layout=layout,
        federated_index=federated_registry,
        layout_details=metrics.get("layout_details", {}),
    )
    return final_exit_code


# ═══════════════════════════════════════════════════════════════════════════════
#  Subcommand: clean
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_clean(args):
    """Remove old workspace runs older than N days."""
    days = args.older_than
    if days < 0:
        print("FAIL: --older-than must be >= 0", file=sys.stderr)
        sys.exit(1)

    cutoff = time.time() - (days * 86400)
    cleaned = 0
    total_bytes = 0

    # Search all candidate workspace locations
    locations = []
    if args.workspace_root:
        locations.append(Path(args.workspace_root))
    locations.extend([
        Path.home() / "Library" / "Caches" / "hongzhi-ai-kit",
        Path.home() / ".cache" / "hongzhi-ai-kit",
        Path("/tmp") / "hongzhi-ai-kit",
    ])

    for base in locations:
        if not base.is_dir():
            continue
        for fp_dir in base.iterdir():
            if not fp_dir.is_dir():
                continue
            for run_dir in fp_dir.iterdir():
                if not run_dir.is_dir():
                    continue
                try:
                    mtime = run_dir.stat().st_mtime
                    if mtime < cutoff:
                        size = sum(f.stat().st_size for f in run_dir.rglob("*") if f.is_file())
                        shutil.rmtree(str(run_dir))
                        cleaned += 1
                        total_bytes += size
                except OSError:
                    pass
            # Remove fingerprint dir if empty
            try:
                if fp_dir.is_dir() and not any(fp_dir.iterdir()):
                    fp_dir.rmdir()
            except OSError:
                pass

    mb = total_bytes / (1024 * 1024)
    print(f"[plugin] clean: removed {cleaned} run(s), freed {mb:.1f} MB")
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
#  Subcommand: status
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_status(args):
    """Show governance status: enabled/disabled, allowlist/denylist, repo check."""
    args_dict = vars(args)
    policy = load_policy_yaml(args_dict)
    global_state_root = resolve_global_state(args, read_only=True)
    index_path = global_state_root / "capability_index.json"
    federated_path = global_state_root / "federated_index.json"
    policy_hash = compute_policy_hash(policy)
    fed_policy = policy.get("federated_index", {}) if isinstance(policy.get("federated_index"), dict) else {}
    fed_enabled = fed_policy.get("enabled")
    if fed_enabled is None:
        fed_enabled = bool(policy.get("enabled", False))

    versions = version_triplet()
    print(f"[plugin] package_version: {versions['package_version']}")
    print(f"[plugin] plugin_version: {versions['plugin_version']}")
    print(f"[plugin] contract_version: {versions['contract_version']}")
    print(f"[plugin] enabled: {policy['enabled']}")
    print(f"[plugin] allow_roots: {policy['allow_roots'] or '(none — all allowed)'}")
    print(f"[plugin] deny_roots: {policy['deny_roots'] or '(none)'}")
    print(f"[plugin] policy_hash: {policy_hash}")
    print(f"[plugin] company_scope: {company_scope_runtime()}")
    print(f"[plugin] company_scope_required: {1 if company_scope_required_runtime() else 0}")
    print(f"[plugin] global_state_root: {global_state_root}")
    print(f"[plugin] capability_index: {index_path}")
    print(f"[plugin] federated_index: {federated_path}")
    print(f"[plugin] federated_index_enabled: {1 if fed_enabled else 0}")
    status_fp = "-"
    if args.repo_root:
        try:
            status_fp = compute_project_fingerprint(Path(args.repo_root).resolve())
        except Exception:
            status_fp = "-"
    status_json = machine_json_field(
        path_value=global_state_root.resolve(),
        command="status",
        repo_fingerprint=status_fp,
        run_id="-",
        extra={
            "enabled": 1 if policy["enabled"] else 0,
            "policy_hash": policy_hash,
            "company_scope_required": 1 if company_scope_required_runtime() else 0,
        },
    )
    status_json_part = f"json={status_json} " if machine_json_enabled() else ""
    print(
        f"HONGZHI_STATUS package_version={versions['package_version']} "
        f"plugin_version={versions['plugin_version']} "
        f"contract_version={versions['contract_version']} "
        f"enabled={1 if policy['enabled'] else 0} "
        f"policy_hash={policy_hash} "
        f"company_scope={quote_machine_value(company_scope_runtime())} "
        f"company_scope_required={1 if company_scope_required_runtime() else 0} "
        f"{status_json_part}"
        f'global_state_root={quote_machine_value(str(global_state_root.resolve()))}'
    )
    if policy.get("_parse_error"):
        detail = str(policy.get("_parse_error_reason", "policy_parse_error"))
        gov_json = machine_json_field(
            path_value="-",
            command="status",
            repo_fingerprint=status_fp,
            run_id="-",
            extra={
                "code": int(POLICY_PARSE_EXIT_CODE),
                "reason": "policy_parse_error",
                "detail": detail,
            },
        )
        gov_json_part = f"json={gov_json} " if machine_json_enabled() else ""
        print(
            f"HONGZHI_GOV_BLOCK code={POLICY_PARSE_EXIT_CODE} reason=policy_parse_error "
            f"command=status "
            f"{gov_json_part}"
            f"company_scope={quote_machine_value(company_scope_runtime())} "
            f"package_version={PACKAGE_VERSION} "
            f"plugin_version={PLUGIN_VERSION} "
            f"contract_version={CONTRACT_VERSION} "
            f"detail={quote_machine_value(detail)}"
        )
        return POLICY_PARSE_EXIT_CODE
    if federated_path.exists():
        print_index_pointer_line(
            federated_path,
            command="status",
            repo_fingerprint=status_fp,
            run_id="-",
        )
    if policy.get("permit_token_file"):
        tok_path = Path(policy["permit_token_file"]).expanduser()
        print(f"[plugin] permit_token_file: {tok_path} ({'found' if tok_path.exists() else 'missing'})")
    
    if args.repo_root:
        repo_root = Path(args.repo_root).resolve()
        fp = compute_project_fingerprint(repo_root)
        latest_path = global_state_root / fp / "latest.json"
        print(f"[plugin] latest_pointer: {latest_path}")
        if not policy["enabled"]:
            print(f"[plugin] repo_root={repo_root}: BLOCKED (plugin disabled)")
            return GOVERNANCE_EXIT_CODE
        else:
            allowed, exit_code, reason, token_used, token_info = check_root_governance(
                policy, repo_root, "status", getattr(args, "permit_token", None))
            status = "ALLOWED" if allowed else "BLOCKED"
            print(f"[plugin] repo_root={repo_root}: {status} ({reason}, exit={exit_code})")
            if token_info.get("provided"):
                print(f"[plugin] token_reason: {token_info.get('validated_reason', token_info.get('reason', 'token_invalid'))}")
            if not allowed:
                return exit_code
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
#  Main — argument parsing
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        prog="hongzhi_plugin",
        description="Hongzhi AI-Kit Plugin Runner — zero-config, read-only-by-default")
    sub = parser.add_subparsers(dest="command", help="Subcommand")

    # ── Common flags via parent parser ──
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace-root", default=None,
                        help="Override workspace root (default: ~/Library/Caches/hongzhi-ai-kit/)")
    common.add_argument("--global-state-root", default=None,
                        help="Override global state root for capability registry")
    common.add_argument("--strict", action="store_true",
                        help="Enforce strict sanity checks (exit non-zero on issues)")
    common.add_argument("--write-ok", action="store_true",
                        help="Explicitly allow writes into project repo (default: false)")
    common.add_argument("--max-files", type=int, default=None,
                        help="Max files for scan stage (read-only snapshot guard remains full)")
    common.add_argument("--max-seconds", type=int, default=None,
                        help="Max seconds for scan (early stop with WARN if hit)")
    common.add_argument("--keywords", default="",
                        help="Disambiguate modules if multiple candidates found")
    common.add_argument("--top-k", type=int, default=5,
                        help="Number of module candidates to report")
    common.add_argument("--kit-root", default=None,
                        help="Path to kit root for policy/tools resolution")
    common.add_argument("--permit-token", default=None,
                        help="One-time token to bypass allowlist/denylist")
    common.add_argument("--machine-json", choices=["0", "1"], default=MACHINE_JSON_CLI_DEFAULT,
                        help="Emit additive machine-line json payload (default: 1, env override via HONGZHI_MACHINE_JSON_ENABLE)")
    common.add_argument("--company-scope", default=COMPANY_SCOPE_DEFAULT,
                        help=f"Company scope marker for machine outputs (default: {COMPANY_SCOPE_DEFAULT}, env override via {COMPANY_SCOPE_ENV})")
    common.add_argument("--require-company-scope", choices=["0", "1"], default="0",
                        help=f"Enable hard gate for company scope match (default: 0, env override via {COMPANY_SCOPE_REQUIRE_ENV})")
    common.add_argument("--smart", action="store_true",
                        help="Enable smart incremental reuse from previous successful run")
    common.add_argument("--smart-max-age-seconds", type=int, default=600,
                        help="Max age (seconds) of prior run allowed for smart reuse")
    common.add_argument("--smart-min-cache-hit", type=float, default=0.90,
                        help="Min cache_hit_rate required to reuse previous run")
    common.add_argument("--smart-max-fingerprint-drift", default="strict", choices=["strict", "warn"],
                        help="Reuse policy when fingerprint/VCS drift is detected")

    index_common = argparse.ArgumentParser(add_help=False)
    index_common.add_argument("--global-state-root", default=None,
                              help="Override global state root for federated index")
    index_common.add_argument("--strict", action="store_true",
                              help="Strict query mode: ignore limits_hit runs unless --include-limits-hit")
    index_common.add_argument("--machine-json", choices=["0", "1"], default=MACHINE_JSON_CLI_DEFAULT,
                              help="Emit additive machine-line json payload (default: 1, env override via HONGZHI_MACHINE_JSON_ENABLE)")
    index_common.add_argument("--company-scope", default=COMPANY_SCOPE_DEFAULT,
                              help=f"Company scope marker for machine outputs (default: {COMPANY_SCOPE_DEFAULT}, env override via {COMPANY_SCOPE_ENV})")
    index_common.add_argument("--require-company-scope", choices=["0", "1"], default="0",
                              help=f"Enable hard gate for company scope match (default: 0, env override via {COMPANY_SCOPE_REQUIRE_ENV})")

    # ── discover ──
    p_disc = sub.add_parser("discover", parents=[common],
                            help="Auto-discover modules, roots, structure, endpoints")
    p_disc.add_argument("--repo-root", required=True, help="Target project root")
    p_disc.add_argument("--min-confidence", type=float, default=0.60,
                        help="Calibration threshold: strict fails with exit=21 when confidence is below this value")
    p_disc.add_argument("--ambiguity-threshold", type=float, default=0.80,
                        help="Calibration ambiguity threshold for top2 score ratio / ambiguity ratio checks")
    p_disc.add_argument("--emit-hints", dest="emit_hints", action="store_true", default=True,
                        help="Emit workspace calibration/hints and discover hint bundle (default: true)")
    p_disc.add_argument("--no-emit-hints", dest="emit_hints", action="store_false",
                        help="Disable optional hint emission (strict needs_human_hint still emits discover hint bundle)")
    p_disc.add_argument("--apply-hints", default="",
                        help="Apply workspace hint bundle (json/yaml) to bias module ranking and root inference")
    p_disc.add_argument("--hint-strategy", default="conservative", choices=["conservative", "aggressive"],
                        help="Hint application strategy when --apply-hints is provided")
    p_disc.add_argument("--allow-cross-repo-hints", action="store_true",
                        help="Allow applying hints with mismatched repo_fingerprint")
    p_disc.add_argument("--hint-bundle-ttl-seconds", type=int, default=1800,
                        help="TTL for emitted profile_delta hint bundle (default: 1800)")

    # ── diff ──
    p_diff = sub.add_parser("diff", parents=[common],
                            help="Cross-project structure diff")
    p_diff.add_argument("--old-project-root", required=True, help="Old repo root")
    p_diff.add_argument("--new-project-root", required=True, help="New repo root")
    p_diff.add_argument("--module-key", default=None, help="Module to diff")
    p_diff.add_argument("--old-scan-graph", default=None,
                        help="Optional old-side scan_graph.json path for cross-command reuse")
    p_diff.add_argument("--new-scan-graph", default=None,
                        help="Optional new-side scan_graph.json path for cross-command reuse")

    # ── profile ──
    p_prof = sub.add_parser("profile", parents=[common],
                            help="Generate effective profile into workspace")
    p_prof.add_argument("--repo-root", required=True, help="Target project root")
    p_prof.add_argument("--module-key", default=None, help="Module key (auto-detected if omitted)")
    p_prof.add_argument("--scan-graph", default=None,
                        help="Optional scan_graph.json path to avoid repeated profile walk")

    # ── migrate ──
    p_mig = sub.add_parser("migrate", parents=[common],
                           help="Pipeline dry-run (read-only)")
    p_mig.add_argument("--repo-root", required=True, help="Target project root")

    # ── scan-graph ──
    p_sg = sub.add_parser("scan-graph", parents=[common],
                          help="Build unified scan graph (workspace-only)")
    p_sg.add_argument("--repo-root", required=True, help="Target project root")
    p_sg.add_argument("--root", action="append", default=[],
                      help="Optional scan root (absolute or repo-relative), repeatable")

    # ── status ──
    p_status = sub.add_parser("status", parents=[common],
                              help="Show governance status (no scan performed)")
    p_status.add_argument("--repo-root", default=None,
                          help="Optional: check if this repo-root is allowed")

    # ── clean ──
    p_clean = sub.add_parser("clean", help="Remove old workspace runs")
    p_clean.add_argument("--older-than", type=int, default=7,
                         help="Remove runs older than N days (default: 7)")
    p_clean.add_argument("--workspace-root", default=None, help="Override workspace root")

    # ── index ──
    p_index = sub.add_parser("index", parents=[index_common],
                             help="Federated capability index operations")
    index_sub = p_index.add_subparsers(dest="index_command", help="Index operation")
    p_idx_list = index_sub.add_parser("list", parents=[index_common], help="List repos in federated index")
    p_idx_list.add_argument("--top-k", type=int, default=20, help="Max repos to list")
    p_idx_query = index_sub.add_parser("query", parents=[index_common], help="Query federated runs")
    p_idx_query.add_argument("--keyword", default="", help="Keyword query against run metadata")
    p_idx_query.add_argument("--endpoint", default="", help="Endpoint path fragment match")
    p_idx_query.add_argument("--top-k", type=int, default=10, help="Max runs to return")
    p_idx_query.add_argument("--include-limits-hit", action="store_true",
                             help="Include runs with limits_hit even in strict query mode")
    p_idx_explain = index_sub.add_parser("explain", parents=[index_common], help="Explain one run in detail")
    p_idx_explain.add_argument("repo_fp", help="Repository fingerprint")
    p_idx_explain.add_argument("run_id", help="Run identifier")

    args = parser.parse_args()
    set_machine_json_runtime(getattr(args, "machine_json", MACHINE_JSON_CLI_DEFAULT))
    set_company_scope_runtime(args)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args._run_command = args.command

    # ── Optional company-scope hard gate (default: disabled) ──
    if args.command != "clean":
        scope_ok, scope_code, scope_reason = check_company_scope_gate(args.command)
        if not scope_ok:
            gov_json = machine_json_field(
                path_value="-",
                command=args.command,
                repo_fingerprint="-",
                run_id="-",
                extra={
                    "code": int(scope_code),
                    "reason": "company_scope_mismatch",
                    "detail": str(scope_reason),
                },
            )
            gov_json_part = f"json={gov_json} " if machine_json_enabled() else ""
            print(
                f"HONGZHI_GOV_BLOCK code={scope_code} reason=company_scope_mismatch "
                f"command={args.command} "
                f"{gov_json_part}"
                f"company_scope={quote_machine_value(company_scope_runtime())} "
                f"package_version={PACKAGE_VERSION} "
                f"plugin_version={PLUGIN_VERSION} "
                f"contract_version={CONTRACT_VERSION} "
                f"detail={quote_machine_value(scope_reason)}"
            )
            sys.exit(scope_code)

    # ── Governance gate (skip for clean/status/help) ──
    if args.command not in ("clean", "status", "index"):
        allowed, exit_code, reason, gov_info = check_governance_full(args)
        if not allowed:
            machine_reason = "governance_blocked"
            if exit_code == GOVERNANCE_EXIT_CODE:
                machine_reason = "plugin_disabled"
                print(f"[plugin] DISABLED: plugin runner requires explicit enable.", file=sys.stderr)
                print(f"[plugin] To enable: export {GOVERNANCE_ENV}=1", file=sys.stderr)
                print(f"[plugin] Or policy.yaml: plugin.enabled: true", file=sys.stderr)
            elif exit_code == GOVERNANCE_DENY_EXIT_CODE:
                machine_reason = "repo_denied"
                print(f"[plugin] BLOCKED: {reason}", file=sys.stderr)
                print(f"[plugin] This repo_root is in the deny_roots list.", file=sys.stderr)
            elif exit_code == GOVERNANCE_ALLOW_EXIT_CODE:
                if "permit-token rejected" in reason:
                    machine_reason = "permit_token_rejected"
                else:
                    machine_reason = "repo_not_allowed"
                print(f"[plugin] BLOCKED: {reason}", file=sys.stderr)
                print(f"[plugin] Add repo path to plugin.allow_roots in policy.yaml.", file=sys.stderr)
            elif exit_code == POLICY_PARSE_EXIT_CODE:
                machine_reason = "policy_parse_error"
                print(f"[plugin] BLOCKED: governance policy parse failed: {reason}", file=sys.stderr)
            gov_json = machine_json_field(
                path_value="-",
                command=args.command,
                repo_fingerprint="-",
                run_id="-",
                extra={
                    "code": int(exit_code),
                    "reason": machine_reason,
                    "detail": str(reason),
                },
            )
            gov_json_part = f"json={gov_json} " if machine_json_enabled() else ""
            # Contract v4: machine-readable governance rejection line on stdout.
            print(
                f"HONGZHI_GOV_BLOCK code={exit_code} reason={machine_reason} "
                f"command={args.command} "
                f"{gov_json_part}"
                f"company_scope={quote_machine_value(company_scope_runtime())} "
                f"package_version={PACKAGE_VERSION} "
                f"plugin_version={PLUGIN_VERSION} "
                f"contract_version={CONTRACT_VERSION} "
                f"detail={quote_machine_value(reason)}"
            )
            sys.exit(exit_code)
        # Attach governance info for capabilities.json
        args._gov_info = gov_info

    # ── Dispatch ──
    dispatch = {
        "discover": cmd_discover,
        "diff": cmd_diff,
        "profile": cmd_profile,
        "migrate": cmd_migrate,
        "scan-graph": cmd_scan_graph,
        "index": cmd_index,
        "status": cmd_status,
        "clean": cmd_clean,
    }
    handler = dispatch.get(args.command)
    if handler:
        rc = handler(args)
        sys.exit(rc or 0)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
