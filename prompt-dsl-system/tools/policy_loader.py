#!/usr/bin/env python3
"""Policy loader for prompt-dsl tools.

Merge priority:
1) hardcoded defaults
2) tools policy.yaml (or explicit --policy)
3) repo overrides (.prompt-dsl-policy.yaml / .prompt-dsl-policy.json)
4) CLI overrides
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

DEFAULT_POLICY_PATH = "prompt-dsl-system/tools/policy.yaml"
DEFAULT_EFFECTIVE_PATH = "prompt-dsl-system/tools/policy_effective.json"
DEFAULT_SOURCES_PATH = "prompt-dsl-system/tools/policy_sources.json"
DEFAULT_MACHINE_POLICY_PATH = "prompt-dsl-system/tools/policy.json"

_RE_INT = re.compile(r"^-?\d+$")
_RE_FLOAT = re.compile(r"^-?\d+\.\d+$")


HARD_DEFAULTS: Dict[str, Any] = {
    "policy_version": "1.0.0",
    "paths": {
        "tools_dir": "prompt-dsl-system/tools",
        "snapshots_dir": "prompt-dsl-system/tools/snapshots",
        "deliveries_dir": "prompt-dsl-system/tools/deliveries",
        "trace_history": "prompt-dsl-system/tools/trace_history.jsonl",
        "validate_report": "prompt-dsl-system/tools/validate_report.json",
        "health_report_json": "prompt-dsl-system/tools/health_report.json",
        "health_report_md": "prompt-dsl-system/tools/health_report.md",
        "health_runbook_md": "prompt-dsl-system/tools/health_runbook.md",
        "health_runbook_sh": "prompt-dsl-system/tools/health_runbook.sh",
        "snapshot_index_json": "prompt-dsl-system/tools/snapshot_index.json",
        "trace_index_json": "prompt-dsl-system/tools/trace_index.json",
    },
    "gates": {
        "verify_gate": {
            "enabled": True,
            "fail_on_fail": True,
            "allow_ack_on_fail": False,
        },
        "loop_gate": {
            "enabled": True,
            "window": 6,
            "fail_on_loop_high": True,
        },
        "guard_gate": {
            "enabled": True,
        },
    },
    "health": {
        "window": 20,
        "runbook_mode": "safe",
        "recommendations_max": 7,
    },
    "snapshots": {
        "enabled_on_apply": True,
        "max_copy_size_mb": 20,
    },
    "prune": {
        "keep_last": 20,
        "max_total_size_mb": 1024,
        "dry_run_default": True,
    },
    "index": {
        "snapshot_limit_md": 500,
        "trace_window": 200,
        "trace_scan_all": False,
        "report_mtime_window_hours": 24,
    },
    "diff": {
        "scan_deliveries_default": False,
        "deliveries_depth": 2,
        "limit_files": 400,
    },
    "bisect": {
        "max_steps": 12,
        "auto_find_good": True,
        "good_verify_top": "PASS",
    },
    "logging": {
        "verbose": False,
    },
}


def _strip_inline_comment(line: str) -> str:
    quote: Optional[str] = None
    out: List[str] = []
    escape = False
    for ch in line:
        if quote is not None:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue

        if ch in {'"', "'"}:
            quote = ch
            out.append(ch)
            continue

        if ch == "#":
            break

        out.append(ch)
    return "".join(out).rstrip()


def _unquote(text: str) -> str:
    s = str(text)
    if len(s) >= 2 and s[0] == s[-1] and s[0] in {"'", '"'}:
        body = s[1:-1]
        if s[0] == '"':
            body = body.replace(r"\\", "\\").replace(r"\"", '"')
        else:
            body = body.replace(r"\\", "\\").replace(r"\'", "'")
        return body
    return s


def _parse_scalar(text: str) -> Any:
    raw = _unquote(str(text).strip())
    lower = raw.lower()
    if lower in {"true", "yes", "on"}:
        return True
    if lower in {"false", "no", "off"}:
        return False
    if lower in {"null", "none", "~"}:
        return None
    if _RE_INT.match(raw):
        try:
            return int(raw)
        except ValueError:
            return raw
    if _RE_FLOAT.match(raw):
        try:
            return float(raw)
        except ValueError:
            return raw
    return raw


def _coerce_recursive(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _coerce_recursive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_coerce_recursive(v) for v in value]
    if isinstance(value, str):
        return _parse_scalar(value)
    return value


def coerce_types(policy: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(policy, dict):
        return {}
    return _coerce_recursive(policy)


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


def _split_key_value(text: str) -> Tuple[str, str]:
    quote: Optional[str] = None
    for idx, ch in enumerate(text):
        if quote is not None:
            if ch == quote:
                quote = None
            continue
        if ch in {'"', "'"}:
            quote = ch
            continue
        if ch == ":":
            left = text[:idx].strip()
            right = text[idx + 1 :].strip()
            return left, right
    return "", ""


def load_yaml_light(path: Union[str, Path]) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return {}

    try:
        raw_lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    root: Dict[str, Any] = {}
    stack: List[Tuple[int, Dict[str, Any]]] = [(-1, root)]

    for raw in raw_lines:
        line = _strip_inline_comment(raw)
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip(" "))
        if indent < 0:
            continue
        content = line.strip()

        key, value = _split_key_value(content)
        if not key:
            continue

        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            stack = [(-1, root)]

        parent = stack[-1][1]
        if value == "":
            child: Dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value)

    return coerce_types(root)


def _has_non_comment_content(path: Path) -> bool:
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = _strip_inline_comment(raw).strip()
            if line:
                return True
    except OSError:
        return False
    return False


def _parse_override_expression(expr: str) -> Tuple[Optional[str], Any]:
    text = str(expr or "").strip()
    if not text or "=" not in text:
        return None, None
    key, raw_val = text.split("=", 1)
    key = key.strip()
    if not key:
        return None, None
    return key, _parse_scalar(raw_val.strip())


def _assign_dotted(target: Dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = [p for p in str(dotted_key).split(".") if p]
    if not parts:
        return
    cur = target
    for part in parts[:-1]:
        node = cur.get(part)
        if not isinstance(node, dict):
            node = {}
            cur[part] = node
        cur = node
    cur[parts[-1]] = value


def parse_cli_overrides(overrides: Sequence[str]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for expr in overrides or []:
        key, value = _parse_override_expression(expr)
        if not key:
            continue
        _assign_dotted(merged, key, value)
    return merged


def build_cli_override_dict(
    repo_root: Path,
    policy_path: Optional[str] = None,
    policy_override_exprs: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    cli_dict = parse_cli_overrides(policy_override_exprs or [])
    raw_path = str(policy_path or "").strip()
    if raw_path:
        p = Path(raw_path)
        if not p.is_absolute():
            p = (Path(repo_root).resolve() / p).resolve()
        else:
            p = p.resolve()
        cli_dict["__policy_path__"] = str(p)
    return cli_dict


def _coerce_cli_override_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (d or {}).items():
        if isinstance(v, dict):
            out[str(k)] = _coerce_cli_override_dict(v)
        elif isinstance(v, list):
            out[str(k)] = [_coerce_recursive(x) for x in v]
        else:
            out[str(k)] = _coerce_recursive(v)
    return out


def _get_nested(d: Dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    cur: Any = d
    for part in str(dotted_key).split("."):
        if not part:
            continue
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur.get(part)
    return cur


def load_policy_meta(
    repo_root: Path,
    cli_overrides: Optional[Union[Dict[str, Any], Sequence[str]]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    repo = Path(repo_root).resolve()

    cli_dict: Dict[str, Any] = {}
    if isinstance(cli_overrides, dict):
        cli_dict = deepcopy(cli_overrides)
    elif isinstance(cli_overrides, (list, tuple)):
        cli_dict = parse_cli_overrides([str(x) for x in cli_overrides])

    explicit_policy_path = _get_nested(cli_dict, "__policy_path__")
    if "__policy_path__" in cli_dict:
        cli_dict.pop("__policy_path__", None)
    if "__policy_override_exprs__" in cli_dict:
        cli_dict.pop("__policy_override_exprs__", None)

    effective = deepcopy(HARD_DEFAULTS)
    sources: Dict[str, Any] = {
        "default": "hardcoded",
        "files": [],
        "cli_overrides": cli_dict,
    }

    base_policy_path = Path(str(explicit_policy_path)).resolve() if explicit_policy_path else (repo / DEFAULT_POLICY_PATH).resolve()
    if base_policy_path.exists() and base_policy_path.is_file():
        parsed = load_yaml_light(base_policy_path)
        loaded = isinstance(parsed, dict) and bool(parsed)
        entry: Dict[str, Any] = {
            "path": str(base_policy_path),
            "kind": "tools_policy_yaml",
            "loaded": loaded,
        }
        if loaded:
            effective = deep_merge(effective, parsed)
        elif _has_non_comment_content(base_policy_path):
            entry["error"] = "parse_empty_or_invalid"
        sources["files"].append(entry)
    else:
        sources["files"].append({"path": str(base_policy_path), "kind": "tools_policy_yaml", "loaded": False})

    repo_yaml = (repo / ".prompt-dsl-policy.yaml").resolve()
    if repo_yaml.exists() and repo_yaml.is_file():
        parsed = load_yaml_light(repo_yaml)
        loaded = isinstance(parsed, dict) and bool(parsed)
        entry = {"path": str(repo_yaml), "kind": "repo_override_yaml", "loaded": loaded}
        if loaded:
            effective = deep_merge(effective, parsed)
        elif _has_non_comment_content(repo_yaml):
            entry["error"] = "parse_empty_or_invalid"
        sources["files"].append(entry)

    repo_json = (repo / ".prompt-dsl-policy.json").resolve()
    if repo_json.exists() and repo_json.is_file():
        try:
            parsed_json = json.loads(repo_json.read_text(encoding="utf-8"))
            if isinstance(parsed_json, dict):
                effective = deep_merge(effective, coerce_types(parsed_json))
                loaded = True
            else:
                loaded = False
        except (OSError, json.JSONDecodeError):
            loaded = False
        sources["files"].append({"path": str(repo_json), "kind": "repo_override_json", "loaded": loaded})

    if cli_dict:
        effective = deep_merge(effective, _coerce_cli_override_dict(cli_dict))

    effective = coerce_types(effective)

    return effective, sources


def load_policy(repo_root: Path, cli_overrides: Optional[Union[Dict[str, Any], Sequence[str]]] = None) -> Dict[str, Any]:
    policy, _sources = load_policy_meta(repo_root, cli_overrides=cli_overrides)
    return policy


def write_policy_artifacts(
    repo_root: Path,
    policy: Dict[str, Any],
    sources: Dict[str, Any],
    tools_dir: Optional[Path] = None,
) -> Dict[str, Path]:
    repo = Path(repo_root).resolve()
    target_tools_dir = tools_dir.resolve() if tools_dir else (repo / "prompt-dsl-system/tools").resolve()
    target_tools_dir.mkdir(parents=True, exist_ok=True)

    effective_path = (target_tools_dir / "policy_effective.json").resolve()
    sources_path = (target_tools_dir / "policy_sources.json").resolve()
    machine_path = (target_tools_dir / "policy.json").resolve()

    effective_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
    sources_path.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    machine_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "policy_effective": effective_path,
        "policy_sources": sources_path,
        "policy_json": machine_path,
    }


def get_policy_value(policy: Dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    cur: Any = policy
    for part in str(dotted_key).split("."):
        if not part:
            continue
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


__all__ = [
    "DEFAULT_POLICY_PATH",
    "load_yaml_light",
    "deep_merge",
    "coerce_types",
    "parse_cli_overrides",
    "build_cli_override_dict",
    "load_policy",
    "load_policy_meta",
    "write_policy_artifacts",
    "get_policy_value",
]
