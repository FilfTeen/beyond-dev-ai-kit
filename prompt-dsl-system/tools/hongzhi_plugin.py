#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Hongzhi AI-Kit Plugin Runner
Version: 3.0.0 (R16 Agent-Native Capability Layer)

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
from typing import Any, Dict, List, Tuple

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

PLUGIN_VERSION = "3.0.0"
SUMMARY_VERSION = "3.0"
GOVERNANCE_ENV = "HONGZHI_PLUGIN_ENABLE"
GOVERNANCE_EXIT_CODE = 10
GOVERNANCE_DENY_EXIT_CODE = 11
GOVERNANCE_ALLOW_EXIT_CODE = 12
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

def check_root_governance(policy, repo_root, permit_token=None):
    """
    Check if repo_root is allowed.
    Returns: (allowed: bool, exit_code: int, reason: str, token_used: bool)
    Priorities:
      1. Permit Token (if valid) -> ALLOW
      2. Deny List -> BLOCK (11)
      3. Allow List (if not empty) -> BLOCK (12) if not present
      4. Default -> ALLOW
    """
    repo_path = str(repo_root.resolve())

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

    if effective_token:
        # Token present — bypass allow/deny (but NOT read-only contract)
        token_used = True
        return True, 0, "permit-token override", True

    # Check Deny List
    for denied in policy["deny_roots"]:
        if repo_path == denied or repo_path.startswith(denied + os.sep):
            return False, GOVERNANCE_DENY_EXIT_CODE, f"repo path denied by policy: {denied}", False

    # Check Allow List
    if policy["allow_roots"]:
        allowed_found = False
        for allowed in policy["allow_roots"]:
            if repo_path == allowed or repo_path.startswith(allowed + os.sep):
                allowed_found = True
                break
        if not allowed_found:
            return False, GOVERNANCE_ALLOW_EXIT_CODE, "repo path not in allow_roots", False
    
    # No allow_roots defined or matched -> allow
    return True, 0, "allowed by policy", False

def check_governance_full(args):
    """Full governance check including enabled status and root validation."""
    args_dict = vars(args)
    policy = load_policy_yaml(args_dict)

    gov_info = {
        "enabled": policy["enabled"],
        "token_used": False,
        "policy_loaded": True
    }

    if not policy["enabled"]:
        return False, GOVERNANCE_EXIT_CODE, "plugin runner disabled", gov_info

    # If repo-root is involved, check it
    repo_root_str = args_dict.get("repo_root")
    if repo_root_str:
        repo_root = Path(repo_root_str).resolve()
        permit_token = args_dict.get("permit_token")
        allowed, code, reason, token_used = check_root_governance(policy, repo_root, permit_token)
        gov_info["token_used"] = token_used
        if not allowed:
             return False, code, reason, gov_info

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
):
    """Write capabilities.json for agent-detectable output (contract v3)."""
    caps = {
        "version": PLUGIN_VERSION,
        "contract_version": SUMMARY_VERSION,
        "command": command,
        "run_id": run_id,
        "repo_fingerprint": repo_fingerprint,
        "timestamp": utc_now_iso(),
        "layout": layout,
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
    }
    cap_path = workspace / "capabilities.json"
    cap_path.write_text(json.dumps(caps, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return cap_path


def print_summary_line(command, fp, run_id, smart_info, metrics, governance):
    """Print single-line agent-detectable summary (fixed key contract)."""
    modules = metrics.get("module_candidates", metrics.get("modules", 0))
    endpoints = metrics.get("endpoints_total", 0)
    scan_time = metrics.get("scan_time_s", 0)
    reused = 1 if smart_info.get("reused") else 0
    reused_from = smart_info.get("reused_from_run_id") or "-"
    gov_state = summarize_governance(governance)
    print(
        "hongzhi_ai_kit_summary "
        f"version={SUMMARY_VERSION} "
        f"command={command} "
        f"fp={fp} "
        f"run_id={run_id} "
        f"smart_reused={reused} "
        f"reused_from={reused_from} "
        f"modules={modules} "
        f"endpoints={endpoints} "
        f"scan_time_s={scan_time} "
        f"governance={gov_state}"
    )


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
    metrics_for_index = dict(metrics)
    # Preserve threshold semantics: absence means unknown; non-positive value is treated as unknown.
    if float(metrics_for_index.get("cache_hit_rate", 0) or 0) <= 0:
        metrics_for_index.pop("cache_hit_rate", None)
    last_success = {
        "run_id": run_id,
        "timestamp": utc_now_iso(),
        "workspace": str(ws),
        "command": command,
    }
    entry_patch = {
        "repo_root": str(repo_root),
        "vcs": {"kind": vcs.get("kind", "none"), "head": vcs.get("head", "none")},
        "last_success": last_success,
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
            "timestamp": utc_now_iso(),
            "repo_fingerprint": fp,
            "repo_root": str(repo_root),
            "workspace": str(ws),
            "command": command,
            "vcs": {"kind": vcs.get("kind", "none"), "head": vcs.get("head", "none")},
            "smart": smart_info,
            "governance": governance,
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
        ensure_endpoints_total(metrics)
    else:
        keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else []
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
            for i, c in enumerate(candidates):
                c["confidence"] = amd.compute_confidence(candidates, i) if candidates else 0
        except Exception as e:
            print(f"[plugin] WARN: auto_module_discover failed: {e}", file=sys.stderr)
            candidates = []
            java_roots = []
            all_pkgs = {}

        metrics["java_roots"] = len(java_roots)
        metrics["module_candidates"] = len(candidates)
        metrics["total_packages"] = len(all_pkgs)

        # ── Self-check: ambiguity ──
        if len(candidates) >= 2 and not keywords:
            top_score = candidates[0]["score"]
            if top_score > 0:
                ratio = candidates[1]["score"] / top_score
                if ratio > 0.8:
                    warn = f"ambiguous modules: top2 score ratio={ratio:.2f} (provide --keywords to disambiguate)"
                    warnings_list.append(warn)
                    print(f"[plugin] WARN: {warn}", file=sys.stderr)
                    if args.strict:
                        print("[plugin] STRICT: ambiguity threshold exceeded, exiting", file=sys.stderr)
                        gov_info = getattr(args, "_gov_info", {})
                        cap_path = write_capabilities(
                            ws,
                            "discover",
                            run_id,
                            fp,
                            layout,
                            [],
                            artifacts_list,
                            metrics,
                            warnings_list,
                            suggestions_list,
                            gov_info,
                            smart_info,
                            capability_registry,
                        )
                        print_summary_line("discover", fp, run_id, smart_info, metrics, gov_info)
                        return 2

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
        else:
            metrics["cache_hit_files"] = 0
            metrics["cache_miss_files"] = 0
            metrics["total_scanned_files"] = 0
            metrics["cache_hit_rate"] = 0.0

        ensure_endpoints_total(metrics)
        roots_info = [
            {"module_key": c.get("module_key"), "package_prefix": c.get("package_prefix")}
            for c in candidates[:5]
        ]
        modules_summary = extract_modules_summary(repo_root, candidates[:5], module_endpoints)

    scan_time = time.time() - t_start
    metrics["scan_time_s"] = round(scan_time, 3)
    metrics["layout"] = layout
    ensure_endpoints_total(metrics)

    # Snapshot after — enforce read-only contract
    snap_after = take_snapshot(repo_root, max_files=args.max_files)
    delta = diff_snapshots(snap_before, snap_after)
    enforce_read_only(delta, args.write_ok)

    gov_info = getattr(args, "_gov_info", {})
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
    )
    print(f"[plugin] capabilities: {cap_path}", file=sys.stderr)
    print(f"[plugin] capability_index: {capability_registry['index_path']}", file=sys.stderr)
    print(f"[plugin] latest_pointer: {capability_registry['latest_path']}", file=sys.stderr)
    print_summary_line("discover", fp, run_id, smart_info, metrics, gov_info)
    return 0


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
    ensure_endpoints_total(metrics)

    gov_info = getattr(args, "_gov_info", {})
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
    print_summary_line("diff", fp, run_id, smart_info, metrics, gov_info)
    return 0


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
    ensure_endpoints_total(metrics)
    gov_info = getattr(args, "_gov_info", {})
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
    cap_path = write_capabilities(
        ws,
        "profile",
        run_id,
        fp,
        detect_layout(repo_root),
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
    print_summary_line("profile", fp, run_id, smart_info, metrics, gov_info)
    return 0


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
    ensure_endpoints_total(metrics)
    gov_info = getattr(args, "_gov_info", {})
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
    cap_path = write_capabilities(
        ws,
        "migrate",
        run_id,
        fp,
        detect_layout(repo_root),
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
    print_summary_line("migrate", fp, run_id, smart_info, metrics, gov_info)
    return 0


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

    print(f"[plugin] version: {PLUGIN_VERSION}")
    print(f"[plugin] enabled: {policy['enabled']}")
    print(f"[plugin] allow_roots: {policy['allow_roots'] or '(none — all allowed)'}")
    print(f"[plugin] deny_roots: {policy['deny_roots'] or '(none)'}")
    print(f"[plugin] global_state_root: {global_state_root}")
    print(f"[plugin] capability_index: {index_path}")
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
            allowed, exit_code, reason, token_used = check_root_governance(
                policy, repo_root, getattr(args, "permit_token", None))
            status = "ALLOWED" if allowed else "BLOCKED"
            print(f"[plugin] repo_root={repo_root}: {status} ({reason}, exit={exit_code})")
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

    # ── Governance gate (skip for clean/status/help) ──
    if args.command not in ("clean", "status"):
        allowed, exit_code, reason, gov_info = check_governance_full(args)
        if not allowed:
            if exit_code == GOVERNANCE_EXIT_CODE:
                print(f"[plugin] DISABLED: plugin runner requires explicit enable.", file=sys.stderr)
                print(f"[plugin] To enable: export {GOVERNANCE_ENV}=1", file=sys.stderr)
                print(f"[plugin] Or policy.yaml: plugin.enabled: true", file=sys.stderr)
            elif exit_code == GOVERNANCE_DENY_EXIT_CODE:
                print(f"[plugin] BLOCKED: {reason}", file=sys.stderr)
                print(f"[plugin] This repo_root is in the deny_roots list.", file=sys.stderr)
            elif exit_code == GOVERNANCE_ALLOW_EXIT_CODE:
                print(f"[plugin] BLOCKED: {reason}", file=sys.stderr)
                print(f"[plugin] Add repo path to plugin.allow_roots in policy.yaml.", file=sys.stderr)
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
