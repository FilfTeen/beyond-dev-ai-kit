#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Hongzhi AI-Kit Plugin Runner
Version: 4.0.0 (R17 Packaging + Agent Contract v4)

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
from hongzhi_ai_kit.paths import resolve_global_state_root, resolve_workspace_root

# ═══════════════════════════════════════════════════════════════════════════════
#  Configuration & Constants
# ═══════════════════════════════════════════════════════════════════════════════

PLUGIN_VERSION = "4.0.0"
CONTRACT_VERSION = "4.0.0"
SUMMARY_VERSION = "3.0"
GOVERNANCE_ENV = "HONGZHI_PLUGIN_ENABLE"
GOVERNANCE_EXIT_CODE = 10
GOVERNANCE_DENY_EXIT_CODE = 11
GOVERNANCE_ALLOW_EXIT_CODE = 12
LIMIT_EXIT_CODE = 20
CALIBRATION_EXIT_CODE = 21
GLOBAL_STATE_ENV = "HONGZHI_PLUGIN_GLOBAL_STATE_ROOT"

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
    canonical = {
        "enabled": bool(policy.get("enabled")),
        "allow_roots": sorted(str(x) for x in (policy.get("allow_roots") or [])),
        "deny_roots": sorted(str(x) for x in (policy.get("deny_roots") or [])),
        "permit_token_file": str(policy.get("permit_token_file") or ""),
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

def load_policy_yaml(args_dict):
    """Load governance policy from policy.yaml (simple parser, no PyYAML dep)."""
    # Try finding kit_root
    kit_root = None
    if args_dict.get("kit_root"):
        kit_root = Path(args_dict["kit_root"])
    else:
        # Infer from script location: tools -> prompt-dsl-system -> beyond-dev-ai-kit
        try:
            kit_root = SCRIPT_DIR.parent.parent
        except Exception:
            pass
    
    policy = {
        "enabled": False,
        "allow_roots": [],
        "deny_roots": [],
        "permit_token_file": None
    }

    # Env override for enable
    if os.environ.get(GOVERNANCE_ENV) == "1":
        policy["enabled"] = True
    
    if kit_root:
        policy_path = kit_root / "policy.yaml"
        if policy_path.exists():
            try:
                # Simple line-based parser to avoid PyYAML dependency
                # Supports subset of YAML used in tests (flow-style lists)
                content = policy_path.read_text(encoding="utf-8")
                in_plugin = False
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    
                    if line == "plugin:":
                        in_plugin = True
                        continue
                    
                    if in_plugin:
                        if line.startswith("enabled:"):
                            val = line.split(":", 1)[1].strip().lower()
                            policy["enabled"] = (val == "true")
                        elif line.startswith("allow_roots:"):
                            # Handle ["..."]
                            val = line.split(":", 1)[1].strip()
                            if val.startswith("[") and val.endswith("]"):
                                items = [x.strip().strip('"\'') for x in val[1:-1].split(",")]
                                policy["allow_roots"] = [str(Path(r).expanduser().resolve()) for r in items if r.strip()]
                        elif line.startswith("deny_roots:"):
                            val = line.split(":", 1)[1].strip()
                            if val.startswith("[") and val.endswith("]"):
                                items = [x.strip().strip('"\'') for x in val[1:-1].split(",")]
                                policy["deny_roots"] = [str(Path(r).expanduser().resolve()) for r in items if r.strip()]
                        elif line.startswith("permit_token_file:"):
                            val = line.split(":", 1)[1].strip().strip('"\'')
                            policy["permit_token_file"] = val
            except Exception:
                pass
    
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

    gov_info = {
        "enabled": policy["enabled"],
        "token_used": False,
        "policy_loaded": True,
        "policy_hash": compute_policy_hash(policy),
        "token_reason": "token_not_provided",
    }

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


def resolve_workspace(fingerprint, run_id, override_root=None):
    """Resolve workspace directory with fallback chain."""
    try:
        workspace_root = resolve_workspace_root(override_root)
        ws = workspace_root / fingerprint / run_id
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
    caps = {
        "version": PLUGIN_VERSION,
        "package_version": versions["package_version"],
        "plugin_version": versions["plugin_version"],
        "contract_version": versions["contract_version"],
        "summary_version": SUMMARY_VERSION,
        "command": command,
        "run_id": run_id,
        "repo_fingerprint": repo_fingerprint,
        "timestamp": utc_now_iso(),
        "layout": layout,
        "module_candidates": as_int(metrics.get("module_candidates", len(roots)), len(roots)),
        "ambiguity_ratio": float(metrics.get("ambiguity_ratio", 0.0) or 0.0),
        "limits_hit": bool(metrics.get("limits_hit", False)),
        "limits": {
            "max_files": limits.get("max_files"),
            "max_seconds": limits.get("max_seconds"),
            "reason": metrics.get("limits_reason", ""),
            "reason_code": metrics.get("limits_reason_code", "-"),
        },
        "scan_stats": scan_stats,
        "calibration": calibration_payload,
        "roots": roots,
        "artifacts": artifacts,
        "metrics": metrics,
        "warnings": warnings,
        "suggestions": suggestions,
        "governance": governance or {},
        "smart": smart or {
            "enabled": False,
            "reused": False,
            "reused_from_run_id": None,
        },
        "capability_registry": capability_registry or {},
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
    cap_path.write_text(json.dumps(caps, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return cap_path


def print_summary_line(command, fp, run_id, smart_info, metrics, governance):
    """Print single-line agent-detectable summary (fixed key contract)."""
    versions = version_triplet()
    modules = metrics.get("module_candidates", metrics.get("modules", 0))
    endpoints = metrics.get("endpoints_total", 0)
    scan_time = metrics.get("scan_time_s", 0)
    reused = 1 if smart_info.get("reused") else 0
    reused_from = smart_info.get("reused_from_run_id") or "-"
    gov_state = summarize_governance(governance)
    limits_hit = 1 if metrics.get("limits_hit") else 0
    limits_reason_code = metrics.get("limits_reason_code", "-")
    needs_human_hint = 1 if metrics.get("needs_human_hint") else 0
    confidence_tier = metrics.get("confidence_tier", "-")
    ambiguity_ratio = float(metrics.get("ambiguity_ratio", 0.0) or 0.0)
    exit_hint = str(metrics.get("exit_hint", "-") or "-")
    print(
        "hongzhi_ai_kit_summary "
        f"version={SUMMARY_VERSION} "
        f"package_version={versions['package_version']} "
        f"plugin_version={versions['plugin_version']} "
        f"contract_version={versions['contract_version']} "
        f"command={command} "
        f"fp={fp} "
        f"run_id={run_id} "
        f"smart_reused={reused} "
        f"reused_from={reused_from} "
        f"needs_human_hint={needs_human_hint} "
        f"confidence_tier={confidence_tier} "
        f"ambiguity_ratio={ambiguity_ratio:.4f} "
        f"exit_hint={exit_hint} "
        f"limits_hit={limits_hit} "
        f"limits_reason={limits_reason_code} "
        f"modules={modules} "
        f"endpoints={endpoints} "
        f"scan_time_s={scan_time} "
        f"governance={gov_state}"
    )


def print_caps_pointer_line(cap_path: Path) -> None:
    """Contract v4 machine-readable pointer to capabilities.json."""
    versions = version_triplet()
    print(
        f"HONGZHI_CAPS {cap_path.resolve()} "
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
        "limits": metrics.get("limits", {"max_files": None, "max_seconds": None}),
        "scan_stats": build_scan_stats(metrics),
        "smart_reused": bool(smart_info.get("reused", False)),
        "reused_from_run_id": smart_info.get("reused_from_run_id"),
        "calibration": calibration if isinstance(calibration, dict) else {},
        "needs_human_hint": bool((calibration or {}).get("needs_human_hint", False)),
        "confidence_tier": str((calibration or {}).get("confidence_tier", "-")),
    }
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
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
    )
    print(f"[plugin] capabilities_jsonl: {jsonl_path}", file=sys.stderr)
    print_caps_pointer_line(cap_path)
    print_summary_line(command, fp, run_id, smart_info, metrics, governance)
    return jsonl_path


def resolve_global_state(args) -> Path:
    override = args.global_state_root or os.environ.get(GLOBAL_STATE_ENV)
    try:
        return resolve_global_state_root(override)
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
    smart_info = {"enabled": bool(args.smart), "reused": False, "reused_from_run_id": None}
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
    }
    smart_info["reused"] = True
    smart_info["reused_from_run_id"] = last_success.get("run_id")
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
    smart_info = {"enabled": bool(args.smart), "reused": False, "reused_from_run_id": None}
    capability_registry = {
        "global_state_root": str(global_state_root),
        "index_path": str(global_state_root / "capability_index.json"),
        "latest_path": "",
        "run_meta_path": "",
        "updated": False,
    }

    # Snapshot before
    snap_before = take_snapshot(repo_root, max_files=args.max_files)

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
        ensure_endpoints_total(metrics)
    else:
        module_endpoints = {}

        # ── Step 1: auto_module_discover ──
        sys.path.insert(0, str(SCRIPT_DIR))
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
            candidates = amd.cluster_modules(all_pkgs, keywords)[:args.top_k]
            discover_candidates = candidates
            for i, c in enumerate(candidates):
                c["confidence"] = amd.compute_confidence(candidates, i) if candidates else 0
        except Exception as e:
            print(f"[plugin] WARN: auto_module_discover failed: {e}", file=sys.stderr)
            candidates = []
            discover_candidates = []
            java_roots = []
            all_pkgs = {}

        metrics["java_roots"] = len(java_roots)
        metrics["module_candidates"] = len(candidates)
        metrics["total_packages"] = len(all_pkgs)

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

        if sd and candidates:
            # Scan once, reuse across candidates
            sd_java_roots, sd_template_roots = sd.find_scan_roots(repo_root)
            all_java_results = []
            total_ch = 0
            total_cm = 0
            for jr in sd_java_roots:
                rh = sd.root_hash(str(jr))
                # Use workspace for cache
                cache_dir = ws / ".structure_cache"
                file_idx = sd.load_file_index(cache_dir, rh)
                results, new_idx, hits, misses = sd.scan_java_root_incremental(jr, repo_root, file_idx)
                all_java_results.extend(results)
                total_ch += hits
                total_cm += misses
                sd.save_file_index(cache_dir, rh, new_idx)

            all_templates = []
            for tr in sd_template_roots:
                all_templates.extend(sd.scan_templates(tr, repo_root))

            clusters = sd.cluster_packages(all_java_results)
            metrics["cache_hit_files"] = total_ch
            metrics["cache_miss_files"] = total_cm
            metrics["total_scanned_files"] = total_ch + total_cm
            metrics["cache_hit_rate"] = compute_cache_hit_rate(total_ch, total_cm)

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
                    warn = f"module '{mk}': {ctrl_count} controller(s) but 0 endpoints — possible parsing miss"
                    warnings_list.append(warn)
                    print(f"[plugin] WARN: {warn}", file=sys.stderr)

                struct_path = disc_dir / f"{mk}.structure.yaml"
                all_paths = [r["rel_path"] for r in all_java_results] + all_templates
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

        ensure_endpoints_total(metrics)
        if not structure_signals["controller_count"] and candidates:
            structure_signals["controller_count"] = sum(int(c.get("controller_count", 0) or 0) for c in candidates[:3])
            structure_signals["service_count"] = sum(int(c.get("service_count", 0) or 0) for c in candidates[:3])
            structure_signals["repository_count"] = sum(int(c.get("repository_count", 0) or 0) for c in candidates[:3])
            structure_signals["endpoint_count"] = int(metrics.get("endpoints_total", 0) or 0)
        structure_signals["endpoint_paths"] = list(dict.fromkeys(structure_signals["endpoint_paths"]))
        structure_signals["templates"] = list(dict.fromkeys(structure_signals["templates"]))
        roots_info = [
            {"module_key": c.get("module_key"), "package_prefix": c.get("package_prefix")}
            for c in candidates[:5]
        ]
        modules_summary = extract_modules_summary(repo_root, candidates[:5], module_endpoints)

    scan_time = time.time() - t_start
    metrics["scan_time_s"] = round(scan_time, 3)
    metrics["layout"] = layout
    metrics.setdefault("module_candidates", len(roots_info))
    metrics.setdefault("ambiguity_ratio", round(float(ambiguity_ratio), 4))
    ensure_endpoints_total(metrics)

    # Snapshot after — enforce read-only contract
    snap_after = take_snapshot(repo_root, max_files=args.max_files)
    delta = diff_snapshots(snap_before, snap_after)
    enforce_read_only(delta, args.write_ok)

    limits_hit, limit_codes, limit_texts = evaluate_limits(args, metrics, scan_time)
    for reason in limit_texts:
        warnings_list.append(f"limits_hit: {reason}")
        print(f"[plugin] WARN: limits_hit: {reason}", file=sys.stderr)
    final_exit_code = 0
    if limits_hit and args.strict:
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
    metrics["exit_hint"] = "-"
    for action in calibration_report.get("action_suggestions", []):
        if action not in suggestions_list:
            suggestions_list.append(action)
    if metrics["needs_human_hint"]:
        reason_text = ",".join(calibration_report.get("reasons", [])) or "needs_human_hint"
        warn = f"needs_human_hint: {reason_text}"
        warnings_list.append(warn)
        print(f"[plugin] WARN: {warn}", file=sys.stderr)
        if args.strict:
            final_exit_code = CALIBRATION_EXIT_CODE
            metrics["exit_hint"] = "needs_human_hint"
            print("[plugin] STRICT: needs_human_hint detected, exiting with code 21", file=sys.stderr)

    gov_info = getattr(args, "_gov_info", {})
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
    cap_path = write_capabilities(
        ws,
        "discover",
        run_id,
        fp,
        layout,
        roots_info,
        artifacts_list,
        metrics,
        warnings_list,
        suggestions_list,
        gov_info,
        smart_info,
        capability_registry,
        calibration_report,
    )
    print(f"[plugin] capabilities: {cap_path}", file=sys.stderr)
    print(f"[plugin] capability_index: {capability_registry['index_path']}", file=sys.stderr)
    print(f"[plugin] latest_pointer: {capability_registry['latest_path']}", file=sys.stderr)
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
    smart_info = {"enabled": bool(args.smart), "reused": False, "reused_from_run_id": None}
    capability_registry = {
        "global_state_root": str(global_state_root),
        "index_path": str(global_state_root / "capability_index.json"),
        "latest_path": "",
        "run_meta_path": "",
        "updated": False,
    }
    metrics = {}

    # Snapshot before (both repos)
    snap_old_before = take_snapshot(old_root, max_files=args.max_files)
    snap_new_before = take_snapshot(new_root, max_files=args.max_files)

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

        old_classes = cpsd.scan_classes(old_root, module_key)
        new_classes = cpsd.scan_classes(new_root, module_key)
        old_templates = cpsd.scan_templates(old_root, module_key)
        new_templates = cpsd.scan_templates(new_root, module_key)

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
    snap_old_after = take_snapshot(old_root, max_files=args.max_files)
    snap_new_after = take_snapshot(new_root, max_files=args.max_files)
    delta_old = diff_snapshots(snap_old_before, snap_old_after)
    delta_new = diff_snapshots(snap_new_before, snap_new_after)
    enforce_read_only(delta_old, args.write_ok)
    enforce_read_only(delta_new, args.write_ok)

    if "scan_time_s" not in metrics:
        metrics["scan_time_s"] = round(time.time() - t_start, 3)
    metrics.setdefault("module_candidates", 1 if metrics.get("module_key") else 0)
    metrics.setdefault("ambiguity_ratio", 0.0)
    ensure_endpoints_total(metrics)
    limits_hit, _limit_codes, limit_texts = evaluate_limits(args, metrics, float(metrics["scan_time_s"]))
    for reason in limit_texts:
        warnings_list.append(f"limits_hit: {reason}")
        print(f"[plugin] WARN: limits_hit: {reason}", file=sys.stderr)
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
    cap_path = write_capabilities(
        ws,
        "diff",
        run_id,
        fp,
        "n/a",
        roots_info,
        artifacts_list,
        metrics,
        warnings_list,
        suggestions_list,
        gov_info,
        smart_info,
        capability_registry,
    )
    print(f"[plugin] capabilities: {cap_path}", file=sys.stderr)
    print(f"[plugin] capability_index: {capability_registry['index_path']}", file=sys.stderr)
    print(f"[plugin] latest_pointer: {capability_registry['latest_path']}", file=sys.stderr)
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
    smart_info = {"enabled": bool(args.smart), "reused": False, "reused_from_run_id": None}
    capability_registry = {
        "global_state_root": str(global_state_root),
        "index_path": str(global_state_root / "capability_index.json"),
        "latest_path": "",
        "run_meta_path": "",
        "updated": False,
    }

    snap_before = take_snapshot(repo_root, max_files=args.max_files)
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
            # Run scanner with output into workspace
            try:
                import module_profile_scanner as mps  # noqa: F401

                print(f"[plugin] generating profile for module: {module_key}", file=sys.stderr)
                prof_file = prof_dir / f"{module_key}.profile.yaml"
                prof_file.write_text(f"# Profile for {module_key}\n", encoding="utf-8")
                artifacts_list.append(str(prof_file))
            except ImportError:
                warnings_list.append("module_profile_scanner not available")

        scan_time = time.time() - t_start
        metrics = {"module_key": module_key or "none", "scan_time_s": round(scan_time, 3), "endpoints_total": 0}
        if module_key:
            modules_summary[module_key] = {
                "package_prefix": module_key,
                "confidence": 1.0,
                "roots": [],
                "endpoints": 0,
            }

    snap_after = take_snapshot(repo_root, max_files=args.max_files)
    delta = diff_snapshots(snap_before, snap_after)
    enforce_read_only(delta, args.write_ok)

    if "scan_time_s" not in metrics:
        metrics["scan_time_s"] = round(time.time() - t_start, 3)
    metrics.setdefault("module_candidates", 1 if metrics.get("module_key") and metrics.get("module_key") != "none" else 0)
    metrics.setdefault("ambiguity_ratio", 0.0)
    ensure_endpoints_total(metrics)
    limits_hit, _limit_codes, limit_texts = evaluate_limits(args, metrics, float(metrics["scan_time_s"]))
    for reason in limit_texts:
        warnings_list.append(f"limits_hit: {reason}")
        print(f"[plugin] WARN: limits_hit: {reason}", file=sys.stderr)
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
    cap_path = write_capabilities(
        ws,
        "profile",
        run_id,
        fp,
        layout,
        roots_info,
        artifacts_list,
        metrics,
        warnings_list,
        suggestions_list,
        gov_info,
        smart_info,
        capability_registry,
    )
    print(f"[plugin] capabilities: {cap_path}", file=sys.stderr)
    print(f"[plugin] capability_index: {capability_registry['index_path']}", file=sys.stderr)
    print(f"[plugin] latest_pointer: {capability_registry['latest_path']}", file=sys.stderr)
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
    smart_info = {"enabled": bool(args.smart), "reused": False, "reused_from_run_id": None}
    capability_registry = {
        "global_state_root": str(global_state_root),
        "index_path": str(global_state_root / "capability_index.json"),
        "latest_path": "",
        "run_meta_path": "",
        "updated": False,
    }

    snap_before = take_snapshot(repo_root, max_files=args.max_files)
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

    snap_after = take_snapshot(repo_root, max_files=args.max_files)
    delta = diff_snapshots(snap_before, snap_after)
    enforce_read_only(delta, args.write_ok)

    if "scan_time_s" not in metrics:
        metrics["scan_time_s"] = round(time.time() - t_start, 3)
    metrics.setdefault("module_candidates", 0)
    metrics.setdefault("ambiguity_ratio", 0.0)
    ensure_endpoints_total(metrics)
    limits_hit, _limit_codes, limit_texts = evaluate_limits(args, metrics, float(metrics["scan_time_s"]))
    for reason in limit_texts:
        warnings_list.append(f"limits_hit: {reason}")
        print(f"[plugin] WARN: limits_hit: {reason}", file=sys.stderr)
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
    cap_path = write_capabilities(
        ws,
        "migrate",
        run_id,
        fp,
        layout,
        roots_info,
        artifacts_list,
        metrics,
        warnings_list,
        suggestions_list,
        gov_info,
        smart_info,
        capability_registry,
    )
    print(f"[plugin] capabilities: {cap_path}", file=sys.stderr)
    print(f"[plugin] capability_index: {capability_registry['index_path']}", file=sys.stderr)
    print(f"[plugin] latest_pointer: {capability_registry['latest_path']}", file=sys.stderr)
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
    global_state_root = resolve_global_state(args)
    index_path = global_state_root / "capability_index.json"
    policy_hash = compute_policy_hash(policy)

    versions = version_triplet()
    print(f"[plugin] package_version: {versions['package_version']}")
    print(f"[plugin] plugin_version: {versions['plugin_version']}")
    print(f"[plugin] contract_version: {versions['contract_version']}")
    print(f"[plugin] enabled: {policy['enabled']}")
    print(f"[plugin] allow_roots: {policy['allow_roots'] or '(none — all allowed)'}")
    print(f"[plugin] deny_roots: {policy['deny_roots'] or '(none)'}")
    print(f"[plugin] policy_hash: {policy_hash}")
    print(f"[plugin] global_state_root: {global_state_root}")
    print(f"[plugin] capability_index: {index_path}")
    print(
        f"HONGZHI_STATUS package_version={versions['package_version']} "
        f"plugin_version={versions['plugin_version']} "
        f"contract_version={versions['contract_version']} "
        f"enabled={1 if policy['enabled'] else 0} "
        f"policy_hash={policy_hash}"
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
                        help="Max files for snapshot (early stop with WARN if hit)")
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
    common.add_argument("--smart", action="store_true",
                        help="Enable smart incremental reuse from previous successful run")
    common.add_argument("--smart-max-age-seconds", type=int, default=600,
                        help="Max age (seconds) of prior run allowed for smart reuse")
    common.add_argument("--smart-min-cache-hit", type=float, default=0.90,
                        help="Min cache_hit_rate required to reuse previous run")
    common.add_argument("--smart-max-fingerprint-drift", default="strict", choices=["strict", "warn"],
                        help="Reuse policy when fingerprint/VCS drift is detected")

    # ── discover ──
    p_disc = sub.add_parser("discover", parents=[common],
                            help="Auto-discover modules, roots, structure, endpoints")
    p_disc.add_argument("--repo-root", required=True, help="Target project root")
    p_disc.add_argument("--min-confidence", type=float, default=0.60,
                        help="Calibration threshold: strict fails with exit=21 when confidence is below this value")
    p_disc.add_argument("--ambiguity-threshold", type=float, default=0.80,
                        help="Calibration ambiguity threshold for top2 score ratio / ambiguity ratio checks")
    p_disc.add_argument("--emit-hints", dest="emit_hints", action="store_true", default=True,
                        help="Emit workspace calibration/hints_suggested.yaml (default: true)")
    p_disc.add_argument("--no-emit-hints", dest="emit_hints", action="store_false",
                        help="Disable emitting calibration hints_suggested.yaml (report files still emitted)")

    # ── diff ──
    p_diff = sub.add_parser("diff", parents=[common],
                            help="Cross-project structure diff")
    p_diff.add_argument("--old-project-root", required=True, help="Old repo root")
    p_diff.add_argument("--new-project-root", required=True, help="New repo root")
    p_diff.add_argument("--module-key", default=None, help="Module to diff")

    # ── profile ──
    p_prof = sub.add_parser("profile", parents=[common],
                            help="Generate effective profile into workspace")
    p_prof.add_argument("--repo-root", required=True, help="Target project root")
    p_prof.add_argument("--module-key", default=None, help="Module key (auto-detected if omitted)")

    # ── migrate ──
    p_mig = sub.add_parser("migrate", parents=[common],
                           help="Pipeline dry-run (read-only)")
    p_mig.add_argument("--repo-root", required=True, help="Target project root")

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

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args._run_command = args.command

    # ── Governance gate (skip for clean/status/help) ──
    if args.command not in ("clean", "status"):
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
            # Contract v4: machine-readable governance rejection line on stdout.
            print(
                f"HONGZHI_GOV_BLOCK code={exit_code} reason={machine_reason} "
                f"command={args.command} "
                f"package_version={PACKAGE_VERSION} "
                f"plugin_version={PLUGIN_VERSION} "
                f"contract_version={CONTRACT_VERSION} "
                f"detail=\"{reason}\""
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
