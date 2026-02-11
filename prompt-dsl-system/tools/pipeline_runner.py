#!/usr/bin/env python3
"""Pipeline runner for prompt-dsl-system orchestration.

Standard-library only implementation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from policy_loader import (
    build_cli_override_dict,
    get_policy_value,
    load_policy_meta,
    write_policy_artifacts,
)


REQUIRED_STEP_PARAMS = ("context_id", "trace_id", "input_artifact_refs")
SENSITIVE_KEY_RE = re.compile(r"(token|secret|password|passwd|api[_-]?key|credential|auth)", re.IGNORECASE)
PROFILE_REL_PATH = "prompt-dsl-system/company_profile.yaml"
GUARD_REL_PATH = "prompt-dsl-system/tools/path_diff_guard.py"
GUARD_REPORT_REL_PATH = "prompt-dsl-system/tools/guard_report.json"
ROLLBACK_HELPER_REL_PATH = "prompt-dsl-system/tools/rollback_helper.py"
MOVE_CONFLICT_RESOLVER_REL_PATH = "prompt-dsl-system/tools/move_conflict_resolver.py"
REF_FOLLOWUP_SCANNER_REL_PATH = "prompt-dsl-system/tools/ref_followup_scanner.py"
FOLLOWUP_PATCH_GENERATOR_REL_PATH = "prompt-dsl-system/tools/followup_patch_generator.py"
FOLLOWUP_VERIFIER_REL_PATH = "prompt-dsl-system/tools/followup_verifier.py"
TRACE_HISTORY_REL_PATH = "prompt-dsl-system/tools/trace_history.jsonl"
LOOP_DETECTOR_REL_PATH = "prompt-dsl-system/tools/loop_detector.py"
RISK_GATE_REL_PATH = "prompt-dsl-system/tools/risk_gate.py"
RISK_TOKEN_JSON_REL_PATH = "prompt-dsl-system/tools/RISK_GATE_TOKEN.json"
ACK_NOTES_REL_PATH = "prompt-dsl-system/tools/ack_notes.py"
HEALTH_REPORTER_REL_PATH = "prompt-dsl-system/tools/health_reporter.py"
HEALTH_RUNBOOK_GENERATOR_REL_PATH = "prompt-dsl-system/tools/health_runbook_generator.py"
SNAPSHOT_MANAGER_REL_PATH = "prompt-dsl-system/tools/snapshot_manager.py"
SNAPSHOT_RESTORE_GUIDE_REL_PATH = "prompt-dsl-system/tools/snapshot_restore_guide.py"
SNAPSHOT_PRUNE_REL_PATH = "prompt-dsl-system/tools/snapshot_prune.py"
SNAPSHOT_INDEXER_REL_PATH = "prompt-dsl-system/tools/snapshot_indexer.py"
SNAPSHOT_OPEN_REL_PATH = "prompt-dsl-system/tools/snapshot_open.py"
TRACE_INDEXER_REL_PATH = "prompt-dsl-system/tools/trace_indexer.py"
TRACE_OPEN_REL_PATH = "prompt-dsl-system/tools/trace_open.py"
TRACE_DIFF_REL_PATH = "prompt-dsl-system/tools/trace_diff.py"
TRACE_BISECT_HELPER_REL_PATH = "prompt-dsl-system/tools/trace_bisect_helper.py"


class ParseError(Exception):
    """Raised when a YAML block cannot be parsed with lightweight parser."""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def count_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        inner = value[1:-1]
        if value[0] == '"':
            inner = inner.replace(r"\"", '"').replace(r"\\", "\\")
        else:
            inner = inner.replace(r"\'", "'").replace(r"\\", "\\")
        return inner
    return value


def split_top_level(text: str, delimiter: str = ",") -> List[str]:
    parts: List[str] = []
    buf: List[str] = []
    quote: Optional[str] = None
    depth = 0
    escape = False

    for ch in text:
        if escape:
            buf.append(ch)
            escape = False
            continue

        if quote:
            buf.append(ch)
            if ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue

        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            continue

        if ch in "[{(":
            depth += 1
            buf.append(ch)
            continue

        if ch in "]})":
            if depth > 0:
                depth -= 1
            buf.append(ch)
            continue

        if ch == delimiter and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            continue

        buf.append(ch)

    if buf:
        parts.append("".join(buf).strip())

    return parts


def split_key_value(text: str) -> Tuple[Optional[str], Optional[str]]:
    quote: Optional[str] = None
    depth = 0
    escape = False

    for idx, ch in enumerate(text):
        if escape:
            escape = False
            continue

        if quote:
            if ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue

        if ch in ("'", '"'):
            quote = ch
            continue

        if ch in "[{(":
            depth += 1
            continue

        if ch in "]})":
            if depth > 0:
                depth -= 1
            continue

        if ch == ":" and depth == 0:
            return text[:idx], text[idx + 1 :]

    return None, None


def parse_scalar(value: str) -> Any:
    raw = value.strip()
    if raw == "":
        return ""

    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        return unquote(raw)

    if raw in ("[]", "[ ]"):
        return []

    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(item) for item in split_top_level(inner, ",") if item.strip()]

    low = raw.lower()
    if low in ("true", "false"):
        return low == "true"

    if low in ("null", "none", "~"):
        return None

    if re.fullmatch(r"-?\d+", raw):
        try:
            return int(raw)
        except ValueError:
            pass

    if re.fullmatch(r"-?\d+\.\d+", raw):
        try:
            return float(raw)
        except ValueError:
            pass

    return raw


def parse_cli_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def strip_inline_comment(value: str) -> str:
    quote: Optional[str] = None
    escape = False
    buf: List[str] = []

    for ch in value:
        if escape:
            buf.append(ch)
            escape = False
            continue

        if quote:
            buf.append(ch)
            if ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue

        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            continue

        if ch == "#":
            break

        buf.append(ch)

    return "".join(buf).rstrip()


def parse_simple_yaml_two_level(text: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    current_section: Optional[str] = None
    lines = text.splitlines()

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = count_indent(line)
        key_raw, value_raw = split_key_value(stripped)
        if key_raw is None:
            raise ParseError(f"Invalid YAML line at {idx}: {stripped}")

        key = unquote(key_raw.strip())
        value = strip_inline_comment((value_raw or "").strip())

        if indent == 0:
            if value == "":
                data[key] = {}
                current_section = key
            else:
                data[key] = parse_scalar(value)
                current_section = None
            continue

        if indent == 2:
            if current_section is None or not isinstance(data.get(current_section), dict):
                raise ParseError(f"Unexpected nested key at line {idx}: {stripped}")
            section = data[current_section]
            if value == "":
                section[key] = {}
            else:
                section[key] = parse_scalar(value)
            continue

        raise ParseError(f"Unsupported indentation at line {idx}: {stripped}")

    return data


def load_company_profile(profile_path: Path) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    if not profile_path.exists():
        warnings.append(f"Company profile not found: {profile_path}")
        return None, warnings

    try:
        raw = profile_path.read_text(encoding="utf-8")
    except OSError as exc:
        warnings.append(f"Company profile read failed: {exc}")
        return None, warnings

    try:
        parsed = parse_simple_yaml_two_level(raw)
    except ParseError as exc:
        warnings.append(f"Company profile parse failed: {exc}")
        return None, warnings

    return parsed, warnings


def profile_effective_defaults(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(profile, dict):
        return {}

    db_execution = profile.get("db_execution")
    if not isinstance(db_execution, dict):
        return {}

    defaults: Dict[str, Any] = {}

    schema_strategy = db_execution.get("default_schema_strategy")
    if schema_strategy not in (None, ""):
        defaults["schema_strategy"] = schema_strategy

    preferred_dm_tool = db_execution.get("preferred_dm_tool")
    preferred_oracle_tool = db_execution.get("preferred_oracle_tool")
    if preferred_dm_tool not in (None, "") or preferred_oracle_tool not in (None, ""):
        if preferred_dm_tool not in (None, "") and preferred_oracle_tool not in (None, ""):
            defaults["execution_tool"] = {
                "dm8": preferred_dm_tool,
                "oracle": preferred_oracle_tool,
            }
        elif preferred_dm_tool not in (None, ""):
            defaults["execution_tool"] = preferred_dm_tool
        else:
            defaults["execution_tool"] = preferred_oracle_tool

    require_precheck_gate = db_execution.get("require_precheck_gate")
    if require_precheck_gate is not None:
        defaults["require_precheck_gate"] = require_precheck_gate

    return defaults


def detect_target_db(params: Dict[str, Any]) -> str:
    target_db = params.get("target_db")
    if isinstance(target_db, str) and target_db.strip():
        target_db_norm = target_db.strip().lower()
        if "oracle" in target_db_norm:
            return "oracle"
        if "dm" in target_db_norm:
            return "dm8"

    objective = params.get("objective")
    if isinstance(objective, str):
        objective_norm = objective.lower()
        if "oracle" in objective_norm:
            return "oracle"
        if "dm8" in objective_norm:
            return "dm8"

    return "dm8"


def choose_profile_execution_tool(profile: Optional[Dict[str, Any]], target_db: str) -> Optional[Any]:
    if not isinstance(profile, dict):
        return None
    db_execution = profile.get("db_execution")
    if not isinstance(db_execution, dict):
        return None

    if target_db == "oracle":
        preferred_oracle_tool = db_execution.get("preferred_oracle_tool")
        if preferred_oracle_tool not in (None, ""):
            return preferred_oracle_tool

    preferred_dm_tool = db_execution.get("preferred_dm_tool")
    if preferred_dm_tool not in (None, ""):
        return preferred_dm_tool

    if target_db != "oracle":
        preferred_oracle_tool = db_execution.get("preferred_oracle_tool")
        if preferred_oracle_tool not in (None, ""):
            return preferred_oracle_tool

    return None


def inject_profile_defaults(
    params: Dict[str, Any], profile: Optional[Dict[str, Any]]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    updated = dict(params)
    injected: Dict[str, Any] = {}

    if not isinstance(profile, dict):
        return updated, injected

    db_execution = profile.get("db_execution")
    if not isinstance(db_execution, dict):
        return updated, injected

    if "schema_strategy" not in updated:
        schema_strategy = db_execution.get("default_schema_strategy")
        if schema_strategy not in (None, ""):
            updated["schema_strategy"] = schema_strategy
            injected["schema_strategy"] = schema_strategy

    if "execution_tool" not in updated:
        target_db = detect_target_db(updated)
        execution_tool = choose_profile_execution_tool(profile, target_db)
        if execution_tool not in (None, ""):
            updated["execution_tool"] = execution_tool
            injected["execution_tool"] = execution_tool

    if "require_precheck_gate" not in updated:
        require_precheck_gate = db_execution.get("require_precheck_gate")
        if require_precheck_gate is not None:
            updated["require_precheck_gate"] = require_precheck_gate
            injected["require_precheck_gate"] = require_precheck_gate

    return updated, injected


def parse_inline_parameters(body: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for part in split_top_level(body, ","):
        if not part:
            continue
        key, value = split_key_value(part)
        if key is None:
            raise ParseError(f"Invalid inline parameter entry: {part}")
        key_name = unquote(key.strip())
        params[key_name] = parse_scalar(value or "")
    return params


def parse_block_parameters(lines: List[str], start_idx: int, base_indent: int) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    i = start_idx + 1

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        indent = count_indent(line)
        if indent <= base_indent:
            break

        stripped = line.strip()
        if stripped.startswith("#"):
            i += 1
            continue
        key, value = split_key_value(stripped)
        if key is None:
            raise ParseError(f"Invalid parameters line: {line.strip()}")

        key_name = unquote(key.strip())
        value = strip_inline_comment((value or "").strip())

        if value == "":
            nested_lines: List[str] = []
            j = i + 1
            while j < len(lines):
                line2 = lines[j]
                if not line2.strip():
                    j += 1
                    continue
                indent2 = count_indent(line2)
                if indent2 <= indent:
                    break
                nested_lines.append(line2.strip())
                j += 1

            if not nested_lines:
                params[key_name] = []
            elif all(item.startswith("- ") for item in nested_lines):
                params[key_name] = [parse_scalar(strip_inline_comment(item[2:].strip())) for item in nested_lines]
            else:
                params[key_name] = "\n".join(nested_lines)
            i = j
            continue

        params[key_name] = parse_scalar(value)
        i += 1

    return params


def parse_yaml_step_block(block_text: str) -> Dict[str, Any]:
    lines = block_text.splitlines()

    skill_match = re.search(r"(?m)^\s*skill\s*:\s*(.+?)\s*$", block_text)
    if not skill_match:
        raise ParseError("Missing required field: skill")
    skill_name = parse_scalar(skill_match.group(1))
    if not isinstance(skill_name, str) or not skill_name:
        raise ParseError("Invalid skill value")

    inline_match = re.search(r"(?m)^\s*parameters\s*:\s*\{(.*)\}\s*$", block_text)
    if inline_match:
        raw_body = inline_match.group(1)
        try:
            params = parse_inline_parameters(raw_body)
        except ParseError:
            params = {"__raw_parameters__": "{" + raw_body.strip() + "}"}
    else:
        param_line_idx = -1
        param_indent = 0
        for idx, line in enumerate(lines):
            m = re.match(r"^(\s*)parameters\s*:\s*$", line)
            if m:
                param_line_idx = idx
                param_indent = len(m.group(1))
                break
        if param_line_idx < 0:
            raise ParseError("Missing required field: parameters")
        params = parse_block_parameters(lines, param_line_idx, param_indent)

    if not isinstance(params, dict):
        raise ParseError("Parameters must be a map")

    return {"skill": skill_name, "parameters": params}


def extract_yaml_blocks(markdown_text: str) -> List[Dict[str, Any]]:
    pattern = re.compile(r"```(?:yaml|yml)\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)
    blocks: List[Dict[str, Any]] = []
    for idx, match in enumerate(pattern.finditer(markdown_text), start=1):
        line_num = markdown_text.count("\n", 0, match.start()) + 1
        blocks.append(
            {
                "index": idx,
                "line": line_num,
                "content": match.group(1).strip("\n"),
            }
        )
    return blocks


def load_registry(registry_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], List[str]]:
    errors: List[str] = []
    if not registry_path.exists():
        return [], {}, [f"Registry not found: {registry_path}"]

    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], {}, [f"Registry JSON parse failed: {exc}"]

    if not isinstance(data, list):
        return [], {}, ["Registry root must be a JSON array"]

    by_name: Dict[str, Dict[str, Any]] = {}
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"Registry entry #{idx + 1} is not an object")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"Registry entry #{idx + 1} has invalid name")
            continue
        if name in by_name:
            errors.append(f"Duplicate skill name in registry: {name}")
            continue
        by_name[name] = item

    return data, by_name, errors


def is_sensitive_key(key: str) -> bool:
    return bool(SENSITIVE_KEY_RE.search(key))


def sanitize_step_for_report(step: Dict[str, Any]) -> Dict[str, Any]:
    params = step.get("parameters", {})
    if not isinstance(params, dict):
        params = {}

    required_presence = {field: field in params for field in REQUIRED_STEP_PARAMS}
    sensitive_fields = [k for k in params.keys() if is_sensitive_key(k)]

    return {
        "step": step.get("step"),
        "skill": step.get("skill"),
        "parameter_keys": sorted(list(params.keys())),
        "required_fields_present": required_presence,
        "sensitive_fields_present": sensitive_fields,
        "sensitive_values_masked": bool(sensitive_fields),
    }


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def resolve_repo_paths(repo_root: Path) -> Dict[str, Path]:
    dsl_root = repo_root / "prompt-dsl-system"
    return {
        "repo_root": repo_root,
        "dsl_root": dsl_root,
        "company_profile": dsl_root / "company_profile.yaml",
        "registry": dsl_root / "05_skill_registry" / "skills.json",
        "pipeline_dir": dsl_root / "04_ai_pipeline_orchestration",
        "tools_dir": dsl_root / "tools",
        "validate_report": dsl_root / "tools" / "validate_report.json",
        "health_report_json": dsl_root / "tools" / "health_report.json",
        "health_report_md": dsl_root / "tools" / "health_report.md",
        "run_plan": dsl_root / "tools" / "run_plan.yaml",
    }


def parse_policy_overrides_from_args(args: argparse.Namespace, repo_root: Path) -> Dict[str, Any]:
    raw_exprs = [str(x) for x in (getattr(args, "policy_override", []) or [])]
    parsed = build_cli_override_dict(
        repo_root=repo_root,
        policy_path=str(getattr(args, "policy", "") or "").strip(),
        policy_override_exprs=raw_exprs,
    )
    parsed["__policy_override_exprs__"] = raw_exprs
    return parsed


def load_effective_policy(
    args: argparse.Namespace, repo_root: Path
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    cli_overrides = parse_policy_overrides_from_args(args, repo_root)
    policy, sources = load_policy_meta(repo_root, cli_overrides=cli_overrides)
    return policy, sources, cli_overrides


def policy_subprocess_args(cli_overrides: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    policy_path = cli_overrides.get("__policy_path__")
    if isinstance(policy_path, str) and policy_path.strip():
        out.extend(["--policy", policy_path.strip()])
    override_exprs = cli_overrides.get("__policy_override_exprs__")
    if isinstance(override_exprs, list):
        for expr in override_exprs:
            text = str(expr or "").strip()
            if text:
                out.extend(["--policy-override", text])
    return out


def assert_repo_root(repo_root: Path) -> bool:
    """Fail-fast guard to ensure commands run under expected repository root."""
    registry_path = repo_root / "prompt-dsl-system" / "05_skill_registry" / "skills.json"
    pipeline_dir = repo_root / "prompt-dsl-system" / "04_ai_pipeline_orchestration"

    ok = True
    if not registry_path.exists():
        ok = False
    if not pipeline_dir.exists() or not pipeline_dir.is_dir():
        ok = False

    if not ok:
        print(
            f"Invalid repo root: {repo_root}. Expected to find prompt-dsl-system/05_skill_registry/skills.json",
            file=sys.stderr,
        )
        if not registry_path.exists():
            print(f"Missing: {registry_path}", file=sys.stderr)
        if not pipeline_dir.exists() or not pipeline_dir.is_dir():
            print(f"Missing directory: {pipeline_dir}", file=sys.stderr)
        print(
            "Suggestion: cd to beyond-dev-ai-kit and rerun the command.",
            file=sys.stderr,
        )

    return ok


def resolve_pipeline_path(repo_root: Path, pipeline_arg: str) -> Path:
    candidate = Path(pipeline_arg)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve()


def looks_like_placeholder(value: str) -> bool:
    s = value.strip()
    if not s:
        return True
    return "{{" in s or "}}" in s or "<MODULE_PATH>" in s or "<module_path>" in s


def normalize_module_path_value(
    module_path_value: str, repo_root: Path, require_exists: bool
) -> Optional[Path]:
    text = module_path_value.strip()
    if not text or looks_like_placeholder(text):
        return None

    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if require_exists and (not candidate.exists() or not candidate.is_dir()):
        return None

    return candidate


def extract_pipeline_global_module_path(text: str, repo_root: Path) -> Optional[Path]:
    stripped = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    for line in stripped.splitlines():
        m = re.match(r"^\s*module_path\s*:\s*(.+?)\s*$", line)
        if not m:
            continue
        raw_value = str(parse_scalar(m.group(1)))
        normalized = normalize_module_path_value(raw_value, repo_root, require_exists=True)
        if normalized:
            return normalized
    return None


def extract_step_module_paths(text: str, repo_root: Path) -> List[Path]:
    results: List[Path] = []
    for block in extract_yaml_blocks(text):
        try:
            parsed = parse_yaml_step_block(block["content"])
        except ParseError:
            continue
        params = parsed.get("parameters", {})
        if not isinstance(params, dict):
            continue
        raw = params.get("module_path")
        if not isinstance(raw, str):
            continue
        normalized = normalize_module_path_value(raw, repo_root, require_exists=True)
        if normalized:
            results.append(normalized)
    return results


def common_module_prefix(paths: List[Path], repo_root: Path) -> Optional[Path]:
    if not paths:
        return None
    if len(paths) == 1:
        return paths[0]

    parts_list = [p.parts for p in paths]
    common: List[str] = []
    for items in zip(*parts_list):
        if all(x == items[0] for x in items):
            common.append(items[0])
        else:
            break

    if not common:
        return None

    prefix = Path(*common).resolve()
    if prefix == repo_root.resolve():
        return None
    if not prefix.exists() or not prefix.is_dir():
        return None
    return prefix


def resolve_effective_module_path(
    cli_module_path: Optional[str], repo_root: Path, pipeline_path: Optional[Path]
) -> Tuple[Optional[Path], str]:
    if cli_module_path:
        normalized = normalize_module_path_value(cli_module_path, repo_root, require_exists=True)
        if normalized is None:
            raise ValueError(f"--module-path is not an existing directory: {cli_module_path}")
        return normalized, "cli"

    if not pipeline_path or not pipeline_path.exists():
        return None, "none"

    text = pipeline_path.read_text(encoding="utf-8")

    global_module = extract_pipeline_global_module_path(text, repo_root)
    if global_module:
        return global_module, "pipeline"

    step_modules = extract_step_module_paths(text, repo_root)
    if not step_modules:
        return None, "none"

    unique_modules = sorted({str(p): p for p in step_modules}.values(), key=lambda p: str(p))
    if len(unique_modules) == 1:
        return unique_modules[0], "pipeline"

    derived = common_module_prefix(unique_modules, repo_root)
    if derived:
        return derived, "derived"

    return None, "none"


def read_guard_report(repo_root: Path, report_path: Optional[Path] = None) -> Dict[str, Any]:
    if report_path is None:
        report_path = (repo_root / GUARD_REPORT_REL_PATH).resolve()
    else:
        report_path = report_path.resolve()
    if not report_path.exists():
        return {}
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def run_path_diff_guard(
    repo_root: Path,
    mode: str,
    module_path: Optional[Path],
    module_path_source: str,
    advisory: bool = False,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    messages: List[str] = []
    if os.environ.get("HONGZHI_GUARD_DISABLE") == "1":
        messages.append("Path Diff Guard disabled by HONGZHI_GUARD_DISABLE=1")
        return True, messages, {}

    guard_script = (repo_root / GUARD_REL_PATH).resolve()
    if not guard_script.exists():
        msg = f"Guard script not found: {guard_script}"
        if mode == "run":
            messages.append(msg)
            return False, messages, {}
        messages.append(msg)
        return True, messages, {}

    cmd = [
        sys.executable,
        str(guard_script),
        "--repo-root",
        str(repo_root),
        "--mode",
        mode,
        "--module-path-source",
        module_path_source,
    ]
    if module_path is not None:
        cmd.extend(["--module-path", str(module_path)])
    if advisory:
        cmd.append("--advisory")

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    guard_report = read_guard_report(repo_root)

    if proc.returncode != 0:
        primary_rule = "unknown"
        violations = guard_report.get("violations", []) if isinstance(guard_report, dict) else []
        if isinstance(violations, list) and violations:
            first = violations[0]
            if isinstance(first, dict):
                file_hint = str(first.get("file", "-"))
                rule_hint = str(first.get("rule", "unknown"))
                primary_rule = f"{rule_hint} ({file_hint})"
        else:
            m = re.search(r"\[guard\]\[violation\]\s+(.+?)\s+\|\s+([^\|]+)\s+\|", proc.stderr)
            if m:
                file_hint = m.group(1).strip()
                rule_hint = m.group(2).strip()
                primary_rule = f"{rule_hint} ({file_hint})"

        messages.append("Guard violation: changed files outside allowed module_path or in forbidden zones")
        messages.append(f"guard exit code: {proc.returncode}")
        messages.append(f"primary rule: {primary_rule}")
        messages.append(f"guard report: {GUARD_REPORT_REL_PATH}")
        messages.append("Next step: provide --module-path or revert out-of-scope changes, then rerun.")
        messages.append("You can generate move plan (preferred) instead of rollback:")
        messages.append(
            "./prompt-dsl-system/tools/run.sh rollback -r . -m <MODULE_PATH> --report prompt-dsl-system/tools/guard_report.json --only-violations true"
        )
        return False, messages, guard_report

    return True, messages, guard_report


def ensure_output_under_tools(output_path: Path, tools_dir: Path) -> None:
    try:
        output_path.resolve().relative_to(tools_dir.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Output path must be under {tools_dir} (got: {output_path})"
        ) from exc


def extract_guardrails_lists(guardrails_path: Path) -> Dict[str, List[str]]:
    data: Dict[str, List[str]] = {
        "forbidden_path_patterns": [],
        "ignore_path_patterns": [],
    }
    if not guardrails_path.exists():
        return data

    section: Optional[str] = None
    for raw in guardrails_path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            if stripped.startswith("forbidden_path_patterns:"):
                section = "forbidden_path_patterns"
            elif stripped.startswith("ignore_path_patterns:"):
                section = "ignore_path_patterns"
            else:
                section = None
            continue

        if indent == 2 and stripped.startswith("- ") and section in data:
            data[section].append(stripped[2:].strip().strip('"').strip("'"))

    return data


def resolve_output_dir_under_tools(output_dir_arg: str, repo_root: Path, tools_dir: Path) -> Path:
    candidate = Path(output_dir_arg)
    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        candidate.relative_to(tools_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"output-dir must be under {tools_dir} (got: {candidate})") from exc

    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def resolve_report_path_under_output_dir(
    repo_root: Path,
    tools_dir: Path,
    output_dir: Path,
    report_arg: str,
) -> Path:
    candidate = Path(report_arg)
    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    ensure_output_under_tools(candidate, tools_dir)
    try:
        candidate.relative_to(output_dir.resolve())
    except ValueError as exc:
        raise ValueError(
            f"report path must be under output-dir {output_dir} (got: {candidate})"
        ) from exc
    return candidate


def copy_guard_report(src_report: Path, target_report: Path) -> None:
    if not src_report.exists():
        return
    target_report.parent.mkdir(parents=True, exist_ok=True)
    if src_report.resolve() == target_report.resolve():
        return
    target_report.write_text(src_report.read_text(encoding="utf-8"), encoding="utf-8")


def try_module_path_from_report(
    repo_root: Path, report_path: Path
) -> Tuple[Optional[Path], str]:
    report = read_guard_report(repo_root, report_path=report_path)
    if not report:
        return None, "none"

    normalized = report.get("module_path_normalized")
    if isinstance(normalized, str) and normalized.strip():
        candidate = normalize_module_path_value(normalized, repo_root, require_exists=True)
        if candidate is not None:
            return candidate, "derived"

    module_abs = report.get("module_path")
    if isinstance(module_abs, str) and module_abs.strip():
        candidate = normalize_module_path_value(module_abs, repo_root, require_exists=True)
        if candidate is not None:
            return candidate, "derived"

    return None, "none"


def extract_guard_metrics(guard_report: Dict[str, Any]) -> Tuple[str, str, int, int, List[str]]:
    if not isinstance(guard_report, dict):
        return "unknown", "unknown", 0, 0, []

    changed_files = guard_report.get("changed_files")
    changed_list = [str(x) for x in changed_files] if isinstance(changed_files, list) else []
    violations = guard_report.get("violations")
    violations_list = violations if isinstance(violations, list) else []

    return (
        str(guard_report.get("decision", "unknown")),
        str(guard_report.get("decision_reason", "unknown")),
        len(changed_list),
        len(violations_list),
        changed_list[:20],
    )


def append_trace_history(repo_root: Path, record: Dict[str, Any]) -> None:
    history_path = (repo_root / TRACE_HISTORY_REL_PATH).resolve()
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    # Best-effort refresh for trace index; never block command flow.
    try:
        trace_indexer = (repo_root / TRACE_INDEXER_REL_PATH).resolve()
        if trace_indexer.exists():
            cmd = [
                sys.executable,
                str(trace_indexer),
                "--repo-root",
                str(repo_root),
                "--tools-dir",
                "prompt-dsl-system/tools",
                "--output-dir",
                "prompt-dsl-system/tools",
                "--window",
                "200",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                print(
                    f"[WARN] trace-index refresh failed after trace append (exit {proc.returncode})",
                    file=sys.stderr,
                )
    except Exception as exc:
        print(f"[WARN] trace-index refresh failed after trace append: {exc}", file=sys.stderr)


def normalize_ack_used(
    ack_source: Optional[str] = None,
    ack: Optional[str] = None,
    ack_file: Optional[str] = None,
    ack_latest: bool = False,
) -> str:
    source = str(ack_source or "").strip().lower()
    if source in {"ack", "ack-file", "ack-latest", "none"}:
        return source
    if ack_latest:
        return "ack-latest"
    if isinstance(ack_file, str) and ack_file.strip():
        return "ack-file"
    if isinstance(ack, str) and ack.strip():
        return "ack"
    return "none"


def parse_verify_snapshot(verify_report_path: Path) -> Tuple[str, Optional[int]]:
    payload = read_json_dict(verify_report_path)
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return "MISSING", None

    status = str(summary.get("status", "MISSING")).strip().upper()
    if status not in {"PASS", "WARN", "FAIL"}:
        status = "MISSING"

    raw_hits = summary.get("hits_total")
    hits_total: Optional[int] = None
    if isinstance(raw_hits, int):
        hits_total = max(raw_hits, 0)
    elif isinstance(raw_hits, float):
        hits_total = max(int(raw_hits), 0)
    return status, hits_total


def parse_verify_from_gate_report(
    gate_report: Dict[str, Any],
    verify_report_path: Optional[Path] = None,
    verify_gate_enabled: bool = True,
    verify_threshold: str = "FAIL",
) -> Dict[str, Any]:
    verify_status = "MISSING"
    verify_hits_total: Optional[int] = None
    verify_gate_required = False
    verify_gate_triggered = False

    if isinstance(gate_report, dict) and gate_report:
        raw_status = str(gate_report.get("verify_status", "MISSING")).strip().upper()
        if raw_status in {"PASS", "WARN", "FAIL"}:
            verify_status = raw_status
        raw_hits = gate_report.get("verify_hits_total")
        if isinstance(raw_hits, int):
            verify_hits_total = max(raw_hits, 0)
        elif isinstance(raw_hits, float):
            verify_hits_total = max(int(raw_hits), 0)
        verify_gate_required = bool(gate_report.get("verify_gate_required", False))
        verify_gate_triggered = verify_gate_required
        return {
            "verify_status": verify_status,
            "verify_hits_total": verify_hits_total,
            "verify_gate_required": verify_gate_required,
            "verify_gate_triggered": verify_gate_triggered,
        }

    if verify_report_path is not None:
        verify_status, verify_hits_total = parse_verify_snapshot(verify_report_path)
        threshold = str(verify_threshold).strip().upper()
        rank = {"PASS": 0, "WARN": 1, "FAIL": 2}
        if threshold not in rank:
            threshold = "FAIL"
        verify_gate_required = bool(verify_gate_enabled) and (
            verify_status in rank and rank[verify_status] >= rank[threshold]
        )
        verify_gate_triggered = False

    return {
        "verify_status": verify_status,
        "verify_hits_total": verify_hits_total,
        "verify_gate_required": verify_gate_required,
        "verify_gate_triggered": verify_gate_triggered,
    }


def detect_blocked_by_from_gate_report(gate_report: Dict[str, Any]) -> str:
    if not isinstance(gate_report, dict) or not gate_report:
        return "risk_gate"
    if bool(gate_report.get("verify_gate_required", False)):
        return "verify_gate"
    return "risk_gate"


def append_ack_note(
    repo_root: Path,
    command: str,
    context_id: str,
    trace_id: str,
    note: Optional[str],
    verify_status: str,
    verify_hits_total: Optional[int],
    ack_used: str,
) -> None:
    if str(verify_status).upper() != "FAIL":
        return
    if str(ack_used).strip().lower() == "none":
        return
    if not isinstance(note, str) or not note.strip():
        print(
            "[WARN] verify status is FAIL and ACK was used; consider adding --ack-note \"<reason>\" for audit trail.",
            file=sys.stderr,
        )
        return

    helper = (repo_root / ACK_NOTES_REL_PATH).resolve()
    if not helper.exists():
        print(f"[WARN] ack_notes helper not found: {helper}", file=sys.stderr)
        return

    cmd = [
        sys.executable,
        str(helper),
        "--repo-root",
        str(repo_root),
        "--command",
        command,
        "--context-id",
        context_id,
        "--trace-id",
        trace_id,
        "--note",
        note.strip(),
    ]
    if isinstance(verify_hits_total, int):
        cmd.extend(["--verify-hits-total", str(verify_hits_total)])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    if proc.returncode != 0:
        print(f"[WARN] failed to write ack note (exit={proc.returncode})", file=sys.stderr)


def build_trace_record(
    repo_root: Path,
    context_id: str,
    trace_id: str,
    command: str,
    pipeline_path: Optional[Path],
    effective_module_path: Optional[Path],
    module_path_source: str,
    guard_report: Dict[str, Any],
    action: str,
    verify_status: str = "MISSING",
    verify_hits_total: Optional[int] = None,
    verify_gate_required: bool = False,
    verify_gate_triggered: bool = False,
    ack_used: str = "none",
    blocked_by: str = "none",
    exit_code: int = 0,
    snapshot_created: bool = False,
    snapshot_path: Optional[str] = None,
    snapshot_label: Optional[str] = None,
) -> Dict[str, Any]:
    guard_decision, guard_reason, changed_count, violations_count, changed_sample = extract_guard_metrics(
        guard_report
    )
    effective_module_rel = (
        to_repo_relative(effective_module_path, repo_root) if effective_module_path else None
    )
    return {
        "timestamp": now_iso(),
        "repo_root": str(repo_root),
        "context_id": context_id,
        "trace_id": trace_id,
        "command": command,
        "pipeline_path": to_repo_relative(pipeline_path, repo_root) if pipeline_path else None,
        "effective_module_path": effective_module_rel,
        "module_path_source": module_path_source,
        "guard_decision": guard_decision,
        "guard_decision_reason": guard_reason,
        "changed_files_count": changed_count,
        "violations_count": violations_count,
        "changed_files_sample": changed_sample,
        "verify_status": verify_status,
        "verify_hits_total": verify_hits_total,
        "verify_gate_required": bool(verify_gate_required),
        "verify_gate_triggered": bool(verify_gate_triggered),
        "ack_used": ack_used,
        "blocked_by": blocked_by,
        "exit_code": int(exit_code),
        "snapshot_created": bool(snapshot_created),
        "snapshot_path": snapshot_path,
        "snapshot_label": snapshot_label,
        "action": action,
    }


def parse_int_arg(value: Any, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < minimum:
        return minimum
    return parsed


def run_loop_detector(
    repo_root: Path,
    output_dir: Path,
    context_id: str,
    trace_id: str,
    pipeline_path: Path,
    effective_module_path: Optional[Path],
    window: int,
    same_trace_only: bool,
    policy_cli_args: Optional[List[str]] = None,
) -> Tuple[bool, Dict[str, Any], List[str]]:
    messages: List[str] = []
    diagnostics: Dict[str, Any] = {}

    detector = (repo_root / LOOP_DETECTOR_REL_PATH).resolve()
    if not detector.exists():
        messages.append(f"loop_detector not found: {detector}")
        return False, diagnostics, messages

    cmd = [
        sys.executable,
        str(detector),
        "--repo-root",
        str(repo_root),
        "--history",
        TRACE_HISTORY_REL_PATH,
        "--context-id",
        context_id,
        "--trace-id",
        trace_id,
        "--pipeline-path",
        to_repo_relative(pipeline_path, repo_root),
        "--window",
        str(window),
        "--same-trace-only",
        "true" if same_trace_only else "false",
        "--output-dir",
        to_repo_relative(output_dir, repo_root),
    ]
    if policy_cli_args:
        cmd.extend(policy_cli_args)
    if effective_module_path is not None:
        cmd.extend(
            ["--effective-module-path", to_repo_relative(effective_module_path, repo_root)]
        )

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    diag_path = output_dir / "loop_diagnostics.json"
    if diag_path.exists():
        try:
            diagnostics = json.loads(diag_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            diagnostics = {}

    if proc.returncode != 0:
        messages.append(f"loop_detector failed with exit code {proc.returncode}")
        return False, diagnostics, messages
    return True, diagnostics, messages


def run_health_reporter(
    repo_root: Path,
    validate_report_path: Path,
    trace_history_path: Path,
    window: int,
    output_dir: Path,
    include_deliveries: bool = False,
    use_rg: bool = True,
    timezone_mode: str = "local",
    policy_cli_args: Optional[List[str]] = None,
) -> Tuple[bool, List[str], Dict[str, str]]:
    messages: List[str] = []
    produced: Dict[str, str] = {}

    script = (repo_root / HEALTH_REPORTER_REL_PATH).resolve()
    if not script.exists():
        messages.append(f"health_reporter not found: {script}")
        return False, messages, produced

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--validate-report",
        to_repo_relative(validate_report_path, repo_root),
        "--trace-history",
        to_repo_relative(trace_history_path, repo_root),
        "--window",
        str(window),
        "--output-dir",
        to_repo_relative(output_dir, repo_root),
        "--include-deliveries",
        "true" if include_deliveries else "false",
        "--use-rg",
        "true" if use_rg else "false",
        "--timezone",
        str(timezone_mode or "local"),
    ]
    if policy_cli_args:
        cmd.extend(policy_cli_args)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    report_json = (output_dir / "health_report.json").resolve()
    report_md = (output_dir / "health_report.md").resolve()
    if report_json.exists():
        produced["health_report_json"] = to_repo_relative(report_json, repo_root)
    if report_md.exists():
        produced["health_report_md"] = to_repo_relative(report_md, repo_root)

    if proc.returncode != 0:
        messages.append(f"health_reporter failed with exit code {proc.returncode}")
        return False, messages, produced
    return True, messages, produced


def run_health_runbook_generator(
    repo_root: Path,
    health_report_path: Path,
    output_dir: Path,
    mode: str = "safe",
    include_ack_flows: bool = True,
    shell: str = "bash",
    emit_sh: bool = True,
    emit_md: bool = True,
    policy_cli_args: Optional[List[str]] = None,
) -> Tuple[bool, List[str], Dict[str, str]]:
    messages: List[str] = []
    produced: Dict[str, str] = {}

    script = (repo_root / HEALTH_RUNBOOK_GENERATOR_REL_PATH).resolve()
    if not script.exists():
        messages.append(f"health_runbook_generator not found: {script}")
        return False, messages, produced

    runbook_mode = str(mode or "safe").strip().lower()
    if runbook_mode not in {"safe", "aggressive"}:
        runbook_mode = "safe"
    shell_mode = str(shell or "bash").strip().lower()
    if shell_mode not in {"bash", "zsh"}:
        shell_mode = "bash"

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--health-report",
        to_repo_relative(health_report_path, repo_root),
        "--output-dir",
        to_repo_relative(output_dir, repo_root),
        "--mode",
        runbook_mode,
        "--include-ack-flows",
        "true" if include_ack_flows else "false",
        "--shell",
        shell_mode,
        "--emit-sh",
        "true" if emit_sh else "false",
        "--emit-md",
        "true" if emit_md else "false",
    ]
    if policy_cli_args:
        cmd.extend(policy_cli_args)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    runbook_json = (output_dir / "health_runbook.json").resolve()
    runbook_md = (output_dir / "health_runbook.md").resolve()
    runbook_sh = (output_dir / "health_runbook.sh").resolve()
    if runbook_json.exists():
        produced["health_runbook_json"] = to_repo_relative(runbook_json, repo_root)
    if runbook_md.exists():
        produced["health_runbook_md"] = to_repo_relative(runbook_md, repo_root)
    if runbook_sh.exists():
        produced["health_runbook_sh"] = to_repo_relative(runbook_sh, repo_root)

    if proc.returncode != 0:
        messages.append(f"health_runbook_generator failed with exit code {proc.returncode}")
        return False, messages, produced
    return True, messages, produced


def run_snapshot_manager(
    repo_root: Path,
    snapshot_dir: Path,
    context_id: Optional[str],
    trace_id: Optional[str],
    label: str,
    includes: Optional[List[Path]] = None,
    max_copy_size_mb: int = 20,
    policy_cli_args: Optional[List[str]] = None,
) -> Tuple[bool, List[str], Dict[str, str]]:
    messages: List[str] = []
    produced: Dict[str, str] = {}

    script = (repo_root / SNAPSHOT_MANAGER_REL_PATH).resolve()
    if not script.exists():
        messages.append(f"snapshot_manager not found: {script}")
        return False, messages, produced

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--output-dir",
        to_repo_relative(snapshot_dir, repo_root),
        "--mode",
        "create",
        "--max-copy-size-mb",
        str(max(1, int(max_copy_size_mb))),
        "--label",
        str(label or "apply"),
    ]
    if policy_cli_args:
        cmd.extend(policy_cli_args)
    if context_id:
        cmd.extend(["--context-id", context_id])
    if trace_id:
        cmd.extend(["--trace-id", trace_id])
    for item in includes or []:
        if item is None:
            continue
        cmd.extend(["--include", to_repo_relative(Path(item), repo_root)])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        value = v.strip()
        if key == "snapshot_path":
            produced["snapshot_path"] = value
        elif key == "manifest_json":
            produced["manifest_json"] = value
        elif key == "manifest_md":
            produced["manifest_md"] = value

    if proc.returncode != 0:
        messages.append(f"snapshot_manager failed with exit code {proc.returncode}")
        return False, messages, produced

    if "snapshot_path" not in produced:
        messages.append("snapshot_manager did not return snapshot_path")
        return False, messages, produced

    # Best-effort index refresh; never block apply flow.
    try:
        index_ok, _index_code, index_messages, index_outputs = run_snapshot_indexer(
            repo_root=repo_root,
            snapshots_dir=(repo_root / "prompt-dsl-system/tools/snapshots").resolve(),
            output_dir=(repo_root / "prompt-dsl-system/tools").resolve(),
            limit=500,
            include_invalid=False,
            now_iso_text="",
            policy_cli_args=policy_cli_args,
        )
        if index_ok:
            if index_outputs.get("snapshot_index_json"):
                messages.append(f"snapshot-index refreshed: {index_outputs['snapshot_index_json']}")
        else:
            for msg in index_messages:
                messages.append(f"snapshot-index refresh warning: {msg}")
    except Exception as exc:  # pragma: no cover - defensive, non-blocking
        messages.append(f"snapshot-index refresh warning: {exc}")

    return True, messages, produced


def run_snapshot_restore_guide(
    repo_root: Path,
    snapshot_path: Path,
    output_dir: Optional[Path],
    shell: str,
    mode: str,
    strict: bool,
    dry_run: bool,
) -> Tuple[bool, int, List[str], Dict[str, Optional[str]]]:
    messages: List[str] = []
    produced: Dict[str, Optional[str]] = {
        "restore_check_json": None,
        "restore_guide_md": None,
        "restore_full_sh": None,
        "restore_files_sh": None,
    }

    script = (repo_root / SNAPSHOT_RESTORE_GUIDE_REL_PATH).resolve()
    if not script.exists():
        messages.append(f"snapshot_restore_guide not found: {script}")
        return False, 2, messages, produced

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--snapshot",
        to_repo_relative(snapshot_path, repo_root),
        "--shell",
        shell,
        "--mode",
        mode,
        "--strict",
        "true" if strict else "false",
        "--dry-run",
        "true" if dry_run else "false",
    ]
    if output_dir is not None:
        cmd.extend(["--output-dir", to_repo_relative(output_dir, repo_root)])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    resolved_output_dir = output_dir if output_dir is not None else (snapshot_path / "restore").resolve()
    check_json = (resolved_output_dir / "restore_check.json").resolve()
    if check_json.exists():
        produced["restore_check_json"] = to_repo_relative(check_json, repo_root)

    if proc.returncode != 0:
        messages.append(f"snapshot_restore_guide exited with code {proc.returncode}")
        return False, proc.returncode, messages, produced

    if mode == "generate":
        guide_md = (resolved_output_dir / "restore_guide.md").resolve()
        full_sh = (resolved_output_dir / "restore_full.sh").resolve()
        files_sh = (resolved_output_dir / "restore_files.sh").resolve()
        if guide_md.exists():
            produced["restore_guide_md"] = to_repo_relative(guide_md, repo_root)
        if full_sh.exists():
            produced["restore_full_sh"] = to_repo_relative(full_sh, repo_root)
        if files_sh.exists():
            produced["restore_files_sh"] = to_repo_relative(files_sh, repo_root)

    return True, 0, messages, produced


def run_snapshot_prune(
    repo_root: Path,
    snapshots_dir: Path,
    output_dir: Path,
    keep_last: int,
    max_total_size_mb: int,
    only_labels: Optional[List[str]],
    exclude_labels: Optional[List[str]],
    dry_run: bool,
    apply: bool,
    now_iso_text: str = "",
    policy_cli_args: Optional[List[str]] = None,
) -> Tuple[bool, int, List[str], Dict[str, Optional[str]]]:
    messages: List[str] = []
    produced: Dict[str, Optional[str]] = {
        "snapshot_prune_report_json": None,
        "snapshot_prune_report_md": None,
    }

    script = (repo_root / SNAPSHOT_PRUNE_REL_PATH).resolve()
    if not script.exists():
        messages.append(f"snapshot_prune not found: {script}")
        return False, 2, messages, produced

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--snapshots-dir",
        to_repo_relative(snapshots_dir, repo_root),
        "--keep-last",
        str(max(0, int(keep_last))),
        "--max-total-size-mb",
        str(max(1, int(max_total_size_mb))),
        "--dry-run",
        "true" if dry_run else "false",
        "--output-dir",
        to_repo_relative(output_dir, repo_root),
    ]
    if policy_cli_args:
        cmd.extend(policy_cli_args)
    if apply:
        cmd.append("--apply")
    for label in only_labels or []:
        text = str(label).strip()
        if text:
            cmd.extend(["--only-label", text])
    for label in exclude_labels or []:
        text = str(label).strip()
        if text:
            cmd.extend(["--exclude-label", text])
    if str(now_iso_text or "").strip():
        cmd.extend(["--now", str(now_iso_text).strip()])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    report_json = (output_dir / "snapshot_prune_report.json").resolve()
    report_md = (output_dir / "snapshot_prune_report.md").resolve()
    if report_json.exists():
        produced["snapshot_prune_report_json"] = to_repo_relative(report_json, repo_root)
    if report_md.exists():
        produced["snapshot_prune_report_md"] = to_repo_relative(report_md, repo_root)

    if proc.returncode != 0:
        messages.append(f"snapshot_prune exited with code {proc.returncode}")
        return False, proc.returncode, messages, produced

    return True, 0, messages, produced


def run_snapshot_indexer(
    repo_root: Path,
    snapshots_dir: Path,
    output_dir: Path,
    limit: int = 500,
    include_invalid: bool = False,
    now_iso_text: str = "",
    policy_cli_args: Optional[List[str]] = None,
) -> Tuple[bool, int, List[str], Dict[str, Optional[str]]]:
    messages: List[str] = []
    produced: Dict[str, Optional[str]] = {
        "snapshot_index_json": None,
        "snapshot_index_md": None,
    }

    script = (repo_root / SNAPSHOT_INDEXER_REL_PATH).resolve()
    if not script.exists():
        messages.append(f"snapshot_indexer not found: {script}")
        return False, 2, messages, produced

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--snapshots-dir",
        to_repo_relative(snapshots_dir, repo_root),
        "--output-dir",
        to_repo_relative(output_dir, repo_root),
        "--limit",
        str(max(1, int(limit))),
        "--include-invalid",
        "true" if include_invalid else "false",
    ]
    if policy_cli_args:
        cmd.extend(policy_cli_args)
    if str(now_iso_text or "").strip():
        cmd.extend(["--now", str(now_iso_text).strip()])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    index_json = (output_dir / "snapshot_index.json").resolve()
    index_md = (output_dir / "snapshot_index.md").resolve()
    if index_json.exists():
        produced["snapshot_index_json"] = to_repo_relative(index_json, repo_root)
    if index_md.exists():
        produced["snapshot_index_md"] = to_repo_relative(index_md, repo_root)

    if proc.returncode != 0:
        messages.append(f"snapshot_indexer exited with code {proc.returncode}")
        return False, proc.returncode, messages, produced
    return True, 0, messages, produced


def run_snapshot_open(
    repo_root: Path,
    index_path: Path,
    snapshots_dir: Path,
    trace_id: str,
    snapshot_id: str,
    context_id: str,
    label: str,
    latest: bool,
    output_format: str,
    emit_restore_guide: bool,
    policy_cli_args: Optional[List[str]] = None,
) -> Tuple[bool, int, List[str], str]:
    messages: List[str] = []

    script = (repo_root / SNAPSHOT_OPEN_REL_PATH).resolve()
    if not script.exists():
        messages.append(f"snapshot_open not found: {script}")
        return False, 2, messages, ""

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--index",
        to_repo_relative(index_path, repo_root),
        "--snapshots-dir",
        to_repo_relative(snapshots_dir, repo_root),
        "--latest",
        "true" if latest else "false",
        "--output",
        output_format,
        "--emit-restore-guide",
        "true" if emit_restore_guide else "false",
    ]
    if policy_cli_args:
        cmd.extend(policy_cli_args)
    if trace_id:
        cmd.extend(["--trace-id", trace_id])
    if snapshot_id:
        cmd.extend(["--snapshot-id", snapshot_id])
    if context_id:
        cmd.extend(["--context-id", context_id])
    if label:
        cmd.extend(["--label", label])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    stdout_text = proc.stdout.strip()
    if stdout_text:
        print(stdout_text)

    if proc.returncode != 0:
        messages.append(f"snapshot_open exited with code {proc.returncode}")
        return False, proc.returncode, messages, stdout_text

    return True, 0, messages, stdout_text


def run_trace_indexer(
    repo_root: Path,
    tools_dir: Path,
    trace_history: Path,
    deliveries_dir: Path,
    snapshots_dir: Path,
    output_dir: Path,
    window: int = 200,
    scan_all: bool = False,
    limit_md: int = 200,
    policy_cli_args: Optional[List[str]] = None,
) -> Tuple[bool, int, List[str], Dict[str, Optional[str]]]:
    messages: List[str] = []
    produced: Dict[str, Optional[str]] = {
        "trace_index_json": None,
        "trace_index_md": None,
    }

    script = (repo_root / TRACE_INDEXER_REL_PATH).resolve()
    if not script.exists():
        messages.append(f"trace_indexer not found: {script}")
        return False, 2, messages, produced

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--tools-dir",
        to_repo_relative(tools_dir, repo_root),
        "--trace-history",
        to_repo_relative(trace_history, repo_root),
        "--deliveries-dir",
        to_repo_relative(deliveries_dir, repo_root),
        "--snapshots-dir",
        to_repo_relative(snapshots_dir, repo_root),
        "--output-dir",
        to_repo_relative(output_dir, repo_root),
        "--window",
        str(max(1, int(window))),
        "--scan-all",
        "true" if scan_all else "false",
        "--limit-md",
        str(max(1, int(limit_md))),
    ]
    if policy_cli_args:
        cmd.extend(policy_cli_args)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    idx_json = (output_dir / "trace_index.json").resolve()
    idx_md = (output_dir / "trace_index.md").resolve()
    if idx_json.exists():
        produced["trace_index_json"] = to_repo_relative(idx_json, repo_root)
    if idx_md.exists():
        produced["trace_index_md"] = to_repo_relative(idx_md, repo_root)

    if proc.returncode != 0:
        messages.append(f"trace_indexer exited with code {proc.returncode}")
        return False, proc.returncode, messages, produced
    return True, 0, messages, produced


def run_trace_open(
    repo_root: Path,
    tools_dir: Path,
    index_path: Path,
    trace_id: str,
    output_format: str = "text",
    emit_restore: bool = True,
    emit_verify: bool = True,
    latest: bool = True,
    policy_cli_args: Optional[List[str]] = None,
) -> Tuple[bool, int, List[str], str]:
    messages: List[str] = []
    script = (repo_root / TRACE_OPEN_REL_PATH).resolve()
    if not script.exists():
        messages.append(f"trace_open not found: {script}")
        return False, 2, messages, ""

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--tools-dir",
        to_repo_relative(tools_dir, repo_root),
        "--index",
        to_repo_relative(index_path, repo_root),
        "--trace-id",
        trace_id,
        "--output",
        output_format,
        "--emit-restore",
        "true" if emit_restore else "false",
        "--emit-verify",
        "true" if emit_verify else "false",
        "--latest",
        "true" if latest else "false",
    ]
    if policy_cli_args:
        cmd.extend(policy_cli_args)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    out_text = proc.stdout.strip()
    if out_text:
        print(out_text)

    if proc.returncode != 0:
        messages.append(f"trace_open exited with code {proc.returncode}")
        return False, proc.returncode, messages, out_text

    return True, 0, messages, out_text


def run_trace_diff(
    repo_root: Path,
    tools_dir: Path,
    index_path: Path,
    trace_a: str,
    trace_b: str,
    latest: bool,
    output_dir: Path,
    scan_deliveries: bool,
    deliveries_depth: int,
    limit_files: int,
    output_format: str,
    policy_cli_args: Optional[List[str]] = None,
) -> Tuple[bool, int, List[str], Dict[str, Optional[str]]]:
    messages: List[str] = []
    produced: Dict[str, Optional[str]] = {
        "trace_diff_json": None,
        "trace_diff_md": None,
    }

    script = (repo_root / TRACE_DIFF_REL_PATH).resolve()
    if not script.exists():
        messages.append(f"trace_diff not found: {script}")
        return False, 2, messages, produced

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--tools-dir",
        to_repo_relative(tools_dir, repo_root),
        "--index",
        to_repo_relative(index_path, repo_root),
        "--a",
        trace_a,
        "--b",
        trace_b,
        "--latest",
        "true" if latest else "false",
        "--output-dir",
        to_repo_relative(output_dir, repo_root),
        "--scan-deliveries",
        "true" if scan_deliveries else "false",
        "--deliveries-depth",
        str(max(0, int(deliveries_depth))),
        "--limit-files",
        str(max(20, int(limit_files))),
        "--format",
        output_format,
    ]
    if policy_cli_args:
        cmd.extend(policy_cli_args)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    out_text = proc.stdout.strip()
    if out_text:
        print(out_text)

    diff_json = (output_dir / "trace_diff.json").resolve()
    diff_md = (output_dir / "trace_diff.md").resolve()
    if diff_json.exists():
        produced["trace_diff_json"] = to_repo_relative(diff_json, repo_root)
    if diff_md.exists():
        produced["trace_diff_md"] = to_repo_relative(diff_md, repo_root)

    if proc.returncode != 0:
        messages.append(f"trace_diff exited with code {proc.returncode}")
        return False, proc.returncode, messages, produced

    return True, 0, messages, produced


def run_trace_bisect_helper(
    repo_root: Path,
    tools_dir: Path,
    index_path: Path,
    bad_trace: str,
    good_trace: str,
    auto_find_good: bool,
    verify_top: str,
    output_dir: Path,
    max_steps: int,
    emit_sh: bool,
    emit_md: bool,
    policy_cli_args: Optional[List[str]] = None,
) -> Tuple[bool, int, List[str], Dict[str, Optional[str]]]:
    messages: List[str] = []
    produced: Dict[str, Optional[str]] = {
        "bisect_plan_json": None,
        "bisect_plan_md": None,
        "bisect_plan_sh": None,
    }

    script = (repo_root / TRACE_BISECT_HELPER_REL_PATH).resolve()
    if not script.exists():
        messages.append(f"trace_bisect_helper not found: {script}")
        return False, 2, messages, produced

    verify = str(verify_top or "PASS").strip().upper()
    if verify not in {"PASS", "WARN", "FAIL", "MISSING"}:
        verify = "PASS"

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--tools-dir",
        to_repo_relative(tools_dir, repo_root),
        "--index",
        to_repo_relative(index_path, repo_root),
        "--bad",
        bad_trace,
        "--auto-find-good",
        "true" if auto_find_good else "false",
        "--verify-top",
        verify,
        "--output-dir",
        to_repo_relative(output_dir, repo_root),
        "--max-steps",
        str(max(5, min(12, int(max_steps)))),
        "--emit-sh",
        "true" if emit_sh else "false",
        "--emit-md",
        "true" if emit_md else "false",
    ]
    if policy_cli_args:
        cmd.extend(policy_cli_args)
    if good_trace:
        cmd.extend(["--good", good_trace])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    out_text = proc.stdout.strip()
    if out_text:
        print(out_text)

    plan_json = (output_dir / "bisect_plan.json").resolve()
    plan_md = (output_dir / "bisect_plan.md").resolve()
    plan_sh = (output_dir / "bisect_plan.sh").resolve()
    if plan_json.exists():
        produced["bisect_plan_json"] = to_repo_relative(plan_json, repo_root)
    if plan_md.exists():
        produced["bisect_plan_md"] = to_repo_relative(plan_md, repo_root)
    if plan_sh.exists():
        produced["bisect_plan_sh"] = to_repo_relative(plan_sh, repo_root)

    if proc.returncode != 0:
        messages.append(f"trace_bisect_helper exited with code {proc.returncode}")
        return False, proc.returncode, messages, produced

    return True, 0, messages, produced


def run_risk_gate_check(
    repo_root: Path,
    guard_report_path: Path,
    loop_report_path: Path,
    move_report_path: Path,
    threshold: str,
    ack: Optional[str],
    ttl_minutes: int,
    exit_code: int,
    token_out: Path,
    token_json_out: Path,
    json_out: Path,
    consume_on_pass: bool,
    verify_report_path: Optional[Path] = None,
    verify_threshold: str = "FAIL",
    verify_as_risk: bool = True,
    verify_required_for: Optional[List[str]] = None,
    command_name: str = "",
    policy_cli_args: Optional[List[str]] = None,
) -> Tuple[bool, int, Dict[str, Any], List[str]]:
    messages: List[str] = []
    report: Dict[str, Any] = {}

    script = (repo_root / RISK_GATE_REL_PATH).resolve()
    if not script.exists():
        messages.append(f"risk_gate not found: {script}")
        return False, 2, report, messages

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--guard-report",
        to_repo_relative(guard_report_path, repo_root),
        "--loop-report",
        to_repo_relative(loop_report_path, repo_root),
        "--move-report",
        to_repo_relative(move_report_path, repo_root),
        "--verify-report",
        to_repo_relative(
            verify_report_path if verify_report_path is not None else (repo_root / "prompt-dsl-system/tools/followup_verify_report.json"),
            repo_root,
        ),
        "--verify-threshold",
        str(verify_threshold).upper(),
        "--verify-as-risk",
        "true" if verify_as_risk else "false",
        "--threshold",
        str(threshold).upper(),
        "--token-out",
        to_repo_relative(token_out, repo_root),
        "--token-json-out",
        to_repo_relative(token_json_out, repo_root),
        "--json-out",
        to_repo_relative(json_out, repo_root),
        "--ttl-minutes",
        str(ttl_minutes),
        "--exit-code",
        str(exit_code),
        "--mode",
        "check",
        "--consume-on-pass",
        "true" if consume_on_pass else "false",
    ]
    if policy_cli_args:
        cmd.extend(policy_cli_args)
    if command_name:
        cmd.extend(["--command-name", command_name])
    if verify_required_for:
        for item in verify_required_for:
            text = str(item).strip()
            if text:
                cmd.extend(["--verify-required-for", text])
    if ack:
        cmd.extend(["--ack", ack])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    if json_out.exists():
        try:
            data = json.loads(json_out.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                report = data
        except (OSError, json.JSONDecodeError):
            report = {}

    if proc.returncode == 0:
        return True, 0, report, messages

    messages.append(f"risk_gate blocked with exit code {proc.returncode}")
    return False, proc.returncode, report, messages


def read_ack_token_from_json_file(token_json_path: Path) -> Optional[str]:
    data = read_json_dict(token_json_path)
    token = data.get("token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    if isinstance(token, dict):
        value = token.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_ack_token(
    repo_root: Path,
    output_dir: Path,
    ack: Optional[str],
    ack_file: Optional[str] = None,
    ack_latest: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    if isinstance(ack, str) and ack.strip():
        return ack.strip(), None

    token_json_path: Optional[Path] = None
    if isinstance(ack_file, str) and ack_file.strip():
        candidate = Path(ack_file.strip())
        if not candidate.is_absolute():
            candidate = (repo_root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        token_json_path = candidate
    elif ack_latest:
        token_json_path = (output_dir / "RISK_GATE_TOKEN.json").resolve()

    if token_json_path is None:
        return None, None
    if not token_json_path.exists() or not token_json_path.is_file():
        return None, f"ack token file not found: {token_json_path}"

    token = read_ack_token_from_json_file(token_json_path)
    if not token:
        return None, f"failed to read ack token from: {token_json_path}"
    return token, None


def refresh_verify_report_if_requested(
    repo_root: Path,
    module_path: Optional[Path],
    move_report_path: Path,
    verify_report_path: Path,
    verify_refresh: bool,
) -> Tuple[bool, List[str]]:
    messages: List[str] = []
    if not verify_refresh:
        return True, messages

    if module_path is None:
        messages.append("verify refresh skipped: module_path is not set")
        return True, messages

    if not move_report_path.exists() or not move_report_path.is_file():
        messages.append(
            f"verify refresh skipped: moves source not found ({to_repo_relative(move_report_path, repo_root)})"
        )
        return True, messages

    verify_output_dir = verify_report_path.parent.resolve()
    ok, code, run_messages, produced = run_followup_verifier(
        repo_root=repo_root,
        moves_path=move_report_path.resolve(),
        output_dir=verify_output_dir,
        mode="full",
        scan_report=None,
        patch_plan=None,
        max_hits=200,
        use_rg=True,
        include_ext=None,
        exclude_dir=None,
    )
    messages.extend(run_messages)
    if not ok:
        messages.append(f"verify refresh failed with exit code {code}")
        return False, messages

    produced_rel = produced.get("followup_verify_report_json")
    if produced_rel:
        generated = (repo_root / produced_rel).resolve()
    else:
        generated = (verify_output_dir / "followup_verify_report.json").resolve()

    if generated.exists() and generated.is_file():
        if generated.resolve() != verify_report_path.resolve():
            verify_report_path.parent.mkdir(parents=True, exist_ok=True)
            verify_report_path.write_text(generated.read_text(encoding="utf-8"), encoding="utf-8")
            messages.append(
                f"verify report refreshed: {to_repo_relative(verify_report_path, repo_root)}"
            )
        else:
            messages.append(f"verify report refreshed: {to_repo_relative(generated, repo_root)}")
    else:
        messages.append("verify refresh completed but report file was not produced")
    return True, messages


def ensure_release_gate(
    repo_root: Path,
    command_name: str,
    module_path: Optional[Path],
    module_path_source: str,
    output_dir: Path,
    guard_report_path: Path,
    loop_report_path: Path,
    move_report_path: Path,
    ack: Optional[str],
    verify_gate_enabled: bool,
    verify_threshold: str,
    verify_report_path: Path,
    verify_refresh: bool,
    risk_gate_enabled: bool = True,
    risk_threshold: str = "HIGH",
    risk_ttl_minutes: int = 30,
    risk_exit_code: int = 4,
    token_out: Optional[Path] = None,
    token_json_out: Optional[Path] = None,
    json_out: Optional[Path] = None,
    consume_on_pass: bool = False,
    policy_cli_args: Optional[List[str]] = None,
) -> Tuple[bool, int, Dict[str, Any], List[str]]:
    messages: List[str] = []
    report: Dict[str, Any] = {}

    if not (risk_gate_enabled or verify_gate_enabled):
        return True, 0, report, messages

    if not risk_gate_enabled:
        guard_report_path.parent.mkdir(parents=True, exist_ok=True)
        guard_report_path.write_text(
            json.dumps(
                {
                    "timestamp": now_iso(),
                    "repo_root": str(repo_root),
                    "decision": "pass",
                    "decision_reason": "risk_gate disabled for guard/loop; verify gate only",
                    "changed_files": [],
                    "violations": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        loop_report_path.parent.mkdir(parents=True, exist_ok=True)
        loop_report_path.write_text(
            json.dumps(
                {
                    "generated_at": now_iso(),
                    "level": "NONE",
                    "triggers": [],
                    "recommendation": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    else:
        if not loop_report_path.exists():
            loop_report_path.parent.mkdir(parents=True, exist_ok=True)
            loop_report_path.write_text(
                json.dumps(
                    {
                        "generated_at": now_iso(),
                        "level": "NONE",
                        "triggers": [],
                        "recommendation": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        if not guard_report_path.exists():
            default_guard_report = (repo_root / GUARD_REPORT_REL_PATH).resolve()
            copy_guard_report(default_guard_report, guard_report_path)

    if verify_gate_enabled:
        refreshed, refresh_messages = refresh_verify_report_if_requested(
            repo_root=repo_root,
            module_path=module_path,
            move_report_path=move_report_path,
            verify_report_path=verify_report_path,
            verify_refresh=verify_refresh,
        )
        messages.extend(refresh_messages)
        if not refreshed:
            return False, risk_exit_code, report, messages

    token_out_path = token_out if token_out is not None else (output_dir / "RISK_GATE_TOKEN.txt").resolve()
    token_json_out_path = (
        token_json_out if token_json_out is not None else (output_dir / "RISK_GATE_TOKEN.json").resolve()
    )
    json_out_path = json_out if json_out is not None else (output_dir / "risk_gate_report.json").resolve()

    gate_ok, gate_code, gate_report, gate_messages = run_risk_gate_check(
        repo_root=repo_root,
        guard_report_path=guard_report_path,
        loop_report_path=loop_report_path,
        move_report_path=move_report_path,
        threshold=str(risk_threshold).upper(),
        ack=ack,
        ttl_minutes=risk_ttl_minutes,
        exit_code=risk_exit_code,
        token_out=token_out_path,
        token_json_out=token_json_out_path,
        json_out=json_out_path,
        consume_on_pass=consume_on_pass,
        verify_report_path=verify_report_path,
        verify_threshold=str(verify_threshold).upper(),
        verify_as_risk=verify_gate_enabled,
        verify_required_for=[command_name],
        command_name=command_name,
        policy_cli_args=policy_cli_args,
    )
    messages.extend(gate_messages)
    report = gate_report
    return gate_ok, gate_code, report, messages


def run_rollback_helper_for_debug_guard(
    repo_root: Path,
    output_dir: Path,
    report_rel_path: str,
    module_path: Optional[Path],
    only_violations: bool,
    plans: str,
    apply_move: bool = False,
    move_dry_run: bool = True,
    yes: bool = False,
    plan_only: bool = False,
    move_mode_apply: bool = False,
) -> Tuple[bool, List[str], Dict[str, Optional[str]]]:
    messages: List[str] = []
    produced: Dict[str, Optional[str]] = {
        "move_plan_md": None,
        "move_plan_sh": None,
        "rollback_plan_md": None,
        "rollback_plan_sh": None,
        "move_apply_log_md": None,
    }

    helper = (repo_root / ROLLBACK_HELPER_REL_PATH).resolve()
    if not helper.exists():
        messages.append(f"rollback_helper not found: {helper}")
        return False, messages, produced

    cmd = [
        sys.executable,
        str(helper),
        "--repo-root",
        str(repo_root),
        "--report",
        report_rel_path,
        "--output-dir",
        to_repo_relative(output_dir, repo_root),
        "--move-output-dir",
        to_repo_relative(output_dir, repo_root),
        "--only-violations",
        "true" if only_violations else "false",
        "--emit",
        plans,
        "--mode",
        "plan",
        "--move-dry-run",
        "true" if move_dry_run else "false",
    ]
    if module_path is not None:
        cmd.extend(["--module-path", str(module_path)])
    if apply_move:
        cmd.extend(["--apply-move", "true"])
    if move_mode_apply:
        cmd.extend(["--move-mode", "apply"])
    if yes:
        cmd.append("--yes")
    if plan_only:
        cmd.extend(["--plan-only", "true"])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    if proc.returncode != 0:
        messages.append(f"rollback_helper failed with exit code {proc.returncode}")
        return False, messages, produced

    move_md = output_dir / "move_plan.md"
    move_sh = output_dir / "move_plan.sh"
    rollback_md = output_dir / "rollback_plan.md"
    rollback_sh = output_dir / "rollback_plan.sh"
    move_apply_log = output_dir / "move_apply_log.md"

    if move_md.exists():
        produced["move_plan_md"] = to_repo_relative(move_md, repo_root)
    if move_sh.exists():
        produced["move_plan_sh"] = to_repo_relative(move_sh, repo_root)
    if rollback_md.exists():
        produced["rollback_plan_md"] = to_repo_relative(rollback_md, repo_root)
    if rollback_sh.exists():
        produced["rollback_plan_sh"] = to_repo_relative(rollback_sh, repo_root)
    if move_apply_log.exists():
        produced["move_apply_log_md"] = to_repo_relative(move_apply_log, repo_root)

    return True, messages, produced


def read_json_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def extract_move_report_summary(move_report: Dict[str, Any]) -> Tuple[int, int, int]:
    summary = move_report.get("summary") if isinstance(move_report.get("summary"), dict) else {}
    total = parse_int_arg(summary.get("total"), default=0, minimum=0)
    non_movable = parse_int_arg(summary.get("non_movable"), default=0, minimum=0)
    high_risk = parse_int_arg(summary.get("high_risk"), default=0, minimum=0)
    return total, non_movable, high_risk


def has_dst_exists_conflict(move_report: Dict[str, Any]) -> bool:
    items = move_report.get("items")
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, dict):
            continue
        flags_raw = item.get("risk_flags")
        flags = [str(x).strip().lower() for x in flags_raw] if isinstance(flags_raw, list) else []
        if "dst_exists" in flags:
            return True
        can_move = bool(item.get("can_move", False))
        deny_reason = str(item.get("deny_reason", "")).strip().lower()
        if (not can_move) and ("dst exists" in deny_reason):
            return True
    return False


def run_move_conflict_resolver(
    repo_root: Path,
    output_dir: Path,
    module_path: Optional[Path],
    mode: str,
    strategy: str,
    yes: bool,
    dry_run: bool,
    ack: Optional[str] = None,
    ack_file: Optional[str] = None,
    ack_latest: bool = False,
    risk_threshold: str = "HIGH",
) -> Tuple[bool, int, List[str], Dict[str, Optional[str]]]:
    messages: List[str] = []
    produced: Dict[str, Optional[str]] = {
        "conflict_plan_md": None,
        "conflict_plan_json": None,
        "rename_script": None,
        "imports_script": None,
        "abort_script": None,
        "conflict_apply_log_md": None,
        "followup_checklist_rename": None,
        "followup_checklist_imports": None,
        "followup_checklist_abort": None,
        "followup_checklist_after_apply": None,
    }

    resolver = (repo_root / MOVE_CONFLICT_RESOLVER_REL_PATH).resolve()
    if not resolver.exists():
        messages.append(f"move_conflict_resolver not found: {resolver}")
        return False, 2, messages, produced

    if module_path is None:
        messages.append("module-path is required for move conflict resolver")
        return False, 2, messages, produced

    cmd = [
        sys.executable,
        str(resolver),
        "--repo-root",
        str(repo_root),
        "--module-path",
        str(module_path),
        "--move-report",
        to_repo_relative(output_dir / "move_report.json", repo_root),
        "--output-dir",
        to_repo_relative(output_dir, repo_root),
        "--mode",
        mode,
        "--strategy",
        strategy,
        "--dry-run",
        "true" if dry_run else "false",
        "--risk-threshold",
        str(risk_threshold).upper(),
        "--guard-report",
        to_repo_relative(output_dir / "guard_report.json", repo_root),
        "--loop-report",
        to_repo_relative(output_dir / "loop_diagnostics.json", repo_root),
    ]
    if yes:
        cmd.append("--yes")
    if ack:
        cmd.extend(["--ack", ack])
    if ack_file:
        cmd.extend(["--ack-file", ack_file])
    if ack_latest:
        cmd.append("--ack-latest")

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    plan_md = output_dir / "conflict_plan.md"
    plan_json = output_dir / "conflict_plan.json"
    rename_sh = output_dir / "conflict_plan_strategy_rename_suffix.sh"
    imports_sh = output_dir / "conflict_plan_strategy_imports_bucket.sh"
    abort_sh = output_dir / "conflict_plan_strategy_abort.sh"
    apply_log = output_dir / "conflict_apply_log.md"
    followup_rename = output_dir / "followup_checklist_rename_suffix.md"
    followup_imports = output_dir / "followup_checklist_imports_bucket.md"
    followup_abort = output_dir / "followup_checklist_abort.md"
    followup_after_apply = output_dir / "followup_checklist_after_apply.md"
    if plan_md.exists():
        produced["conflict_plan_md"] = to_repo_relative(plan_md, repo_root)
    if plan_json.exists():
        produced["conflict_plan_json"] = to_repo_relative(plan_json, repo_root)
    if rename_sh.exists():
        produced["rename_script"] = to_repo_relative(rename_sh, repo_root)
    if imports_sh.exists():
        produced["imports_script"] = to_repo_relative(imports_sh, repo_root)
    if abort_sh.exists():
        produced["abort_script"] = to_repo_relative(abort_sh, repo_root)
    if apply_log.exists():
        produced["conflict_apply_log_md"] = to_repo_relative(apply_log, repo_root)
    if followup_rename.exists():
        produced["followup_checklist_rename"] = to_repo_relative(followup_rename, repo_root)
    if followup_imports.exists():
        produced["followup_checklist_imports"] = to_repo_relative(followup_imports, repo_root)
    if followup_abort.exists():
        produced["followup_checklist_abort"] = to_repo_relative(followup_abort, repo_root)
    if followup_after_apply.exists():
        produced["followup_checklist_after_apply"] = to_repo_relative(followup_after_apply, repo_root)

    if proc.returncode != 0:
        messages.append(f"move_conflict_resolver exited with code {proc.returncode}")
        return False, proc.returncode, messages, produced
    return True, 0, messages, produced


def run_ref_followup_scanner(
    repo_root: Path,
    moves_path: Path,
    output_dir: Path,
    mode: str = "plan",
    max_hits_per_move: int = 50,
) -> Tuple[bool, int, List[str], Dict[str, Optional[str]]]:
    messages: List[str] = []
    produced: Dict[str, Optional[str]] = {
        "followup_scan_report": None,
        "followup_checklist": None,
    }

    scanner = (repo_root / REF_FOLLOWUP_SCANNER_REL_PATH).resolve()
    if not scanner.exists():
        messages.append(f"ref_followup_scanner not found: {scanner}")
        return False, 2, messages, produced

    cmd = [
        sys.executable,
        str(scanner),
        "--repo-root",
        str(repo_root),
        "--moves",
        to_repo_relative(moves_path, repo_root),
        "--output-dir",
        to_repo_relative(output_dir, repo_root),
        "--mode",
        mode,
        "--max-hits-per-move",
        str(max_hits_per_move),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    report_path = output_dir / "followup_scan_report.json"
    checklist_path = output_dir / "followup_checklist.md"
    if report_path.exists():
        produced["followup_scan_report"] = to_repo_relative(report_path, repo_root)
    if checklist_path.exists():
        produced["followup_checklist"] = to_repo_relative(checklist_path, repo_root)

    if proc.returncode != 0:
        messages.append(f"ref_followup_scanner exited with code {proc.returncode}")
        return False, proc.returncode, messages, produced

    return True, 0, messages, produced


def run_followup_patch_generator(
    repo_root: Path,
    scan_report_path: Path,
    output_dir: Path,
    mode: str,
    yes: bool,
    dry_run: bool,
    max_changes: int,
    confidence_threshold: str,
    include_ext: Optional[List[str]] = None,
    exclude_path: Optional[List[str]] = None,
    ack: Optional[str] = None,
    ack_file: Optional[str] = None,
    ack_latest: bool = False,
    risk_threshold: str = "HIGH",
) -> Tuple[bool, int, List[str], Dict[str, Optional[str]]]:
    messages: List[str] = []
    produced: Dict[str, Optional[str]] = {
        "followup_patch_plan_json": None,
        "followup_patch_plan_md": None,
        "followup_patch_diff": None,
        "followup_patch_apply_log": None,
    }

    tool = (repo_root / FOLLOWUP_PATCH_GENERATOR_REL_PATH).resolve()
    if not tool.exists():
        messages.append(f"followup_patch_generator not found: {tool}")
        return False, 2, messages, produced

    cmd = [
        sys.executable,
        str(tool),
        "--repo-root",
        str(repo_root),
        "--scan-report",
        to_repo_relative(scan_report_path, repo_root),
        "--output-dir",
        to_repo_relative(output_dir, repo_root),
        "--mode",
        mode,
        "--dry-run",
        "true" if dry_run else "false",
        "--max-changes",
        str(max_changes),
        "--confidence-threshold",
        confidence_threshold,
        "--risk-threshold",
        str(risk_threshold).upper(),
    ]
    if yes:
        cmd.append("--yes")
    if include_ext:
        for ext in include_ext:
            cmd.extend(["--include-ext", ext])
    if exclude_path:
        for p in exclude_path:
            cmd.extend(["--exclude-path", p])
    if ack:
        cmd.extend(["--ack", ack])
    if ack_file:
        cmd.extend(["--ack-file", ack_file])
    if ack_latest:
        cmd.append("--ack-latest")

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    plan_json = output_dir / "followup_patch_plan.json"
    plan_md = output_dir / "followup_patch_plan.md"
    patch_diff = output_dir / "followup_patch.diff"
    apply_log = output_dir / "followup_patch_apply_log.md"
    if plan_json.exists():
        produced["followup_patch_plan_json"] = to_repo_relative(plan_json, repo_root)
    if plan_md.exists():
        produced["followup_patch_plan_md"] = to_repo_relative(plan_md, repo_root)
    if patch_diff.exists():
        produced["followup_patch_diff"] = to_repo_relative(patch_diff, repo_root)
    if apply_log.exists():
        produced["followup_patch_apply_log"] = to_repo_relative(apply_log, repo_root)

    if proc.returncode != 0:
        messages.append(f"followup_patch_generator exited with code {proc.returncode}")
        return False, proc.returncode, messages, produced

    return True, 0, messages, produced


def run_followup_verifier(
    repo_root: Path,
    moves_path: Path,
    output_dir: Path,
    mode: str = "full",
    scan_report: Optional[Path] = None,
    patch_plan: Optional[Path] = None,
    max_hits: int = 200,
    use_rg: bool = True,
    include_ext: Optional[List[str]] = None,
    exclude_dir: Optional[List[str]] = None,
) -> Tuple[bool, int, List[str], Dict[str, Optional[str]]]:
    messages: List[str] = []
    produced: Dict[str, Optional[str]] = {
        "followup_verify_report_json": None,
        "followup_verify_report_md": None,
    }

    tool = (repo_root / FOLLOWUP_VERIFIER_REL_PATH).resolve()
    if not tool.exists():
        messages.append(f"followup_verifier not found: {tool}")
        return False, 2, messages, produced

    cmd = [
        sys.executable,
        str(tool),
        "--repo-root",
        str(repo_root),
        "--moves",
        to_repo_relative(moves_path, repo_root),
        "--output-dir",
        to_repo_relative(output_dir, repo_root),
        "--mode",
        mode,
        "--max-hits",
        str(max_hits),
        "--use-rg",
        "true" if use_rg else "false",
    ]
    if scan_report is not None:
        cmd.extend(["--scan-report", to_repo_relative(scan_report, repo_root)])
    if patch_plan is not None:
        cmd.extend(["--patch-plan", to_repo_relative(patch_plan, repo_root)])
    if include_ext:
        for ext in include_ext:
            cmd.extend(["--include-ext", ext])
    if exclude_dir:
        for d in exclude_dir:
            cmd.extend(["--exclude-dir", d])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    report_json = output_dir / "followup_verify_report.json"
    report_md = output_dir / "followup_verify_report.md"
    if report_json.exists():
        produced["followup_verify_report_json"] = to_repo_relative(report_json, repo_root)
    if report_md.exists():
        produced["followup_verify_report_md"] = to_repo_relative(report_md, repo_root)

    if proc.returncode != 0:
        messages.append(f"followup_verifier exited with code {proc.returncode}")
        return False, proc.returncode, messages, produced

    return True, 0, messages, produced


def cmd_debug_guard(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)

    pipeline_path: Optional[Path] = None
    if args.pipeline:
        pipeline_path = resolve_pipeline_path(repo_root, args.pipeline)
        if not pipeline_path.exists():
            print(f"Pipeline file not found: {pipeline_path}", file=sys.stderr)
            return 2

    generate_plans = parse_cli_bool(args.generate_plans, default=True)
    only_violations = parse_cli_bool(args.only_violations, default=True)
    plans = args.plans
    if plans not in {"move", "rollback", "both"}:
        print(f"Invalid --plans value: {plans}", file=sys.stderr)
        return 2

    try:
        output_dir = resolve_output_dir_under_tools(args.output_dir, repo_root, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        effective_module_path, module_path_source = resolve_effective_module_path(
            args.module_path, repo_root, pipeline_path
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    guard_ok, guard_messages, guard_report = run_path_diff_guard(
        repo_root=repo_root,
        mode="debug-guard",
        module_path=effective_module_path,
        module_path_source=module_path_source,
        advisory=True,
    )
    _ = guard_ok

    guardrails_path = repo_root / "prompt-dsl-system" / "tools" / "guardrails.yaml"
    lists = extract_guardrails_lists(guardrails_path)

    forbidden_patterns = lists.get("forbidden_path_patterns", [])
    if not forbidden_patterns and isinstance(guard_report.get("effective_rules"), dict):
        fp = guard_report["effective_rules"].get("forbidden_patterns")
        if isinstance(fp, list):
            forbidden_patterns = [str(x) for x in fp]

    ignore_patterns = lists.get("ignore_path_patterns", [])
    if not ignore_patterns:
        ip = guard_report.get("ignore_patterns")
        if isinstance(ip, list):
            ignore_patterns = [str(x) for x in ip]

    normalized_module = guard_report.get("module_path_normalized")
    if normalized_module is None:
        normalized_module = (
            to_repo_relative(effective_module_path, repo_root) if effective_module_path else None
        )

    allow_prompt_dsl = True
    effective_rules = guard_report.get("effective_rules")
    if isinstance(effective_rules, dict):
        allow_prompt_dsl = bool(effective_rules.get("allow_prompt_dsl_system", True))

    allowed_paths = []
    if allow_prompt_dsl:
        allowed_paths.append("prompt-dsl-system/**")
    if normalized_module:
        if str(normalized_module) == ".":
            allowed_paths.append("./**")
        else:
            allowed_paths.append(f"{normalized_module}/**")
    allowed_paths = list(dict.fromkeys(allowed_paths))

    print("Debug Guard Summary")
    print(f"- guardrails: {to_repo_relative(guardrails_path, repo_root)}")
    print("- forbidden patterns:")
    if forbidden_patterns:
        for p in forbidden_patterns:
            print(f"  - {p}")
    else:
        print("  - (none)")

    print("- ignore patterns:")
    if ignore_patterns:
        for p in ignore_patterns:
            print(f"  - {p}")
    else:
        print("  - (none)")

    print(f"- effective_module_path: {normalized_module if normalized_module else 'null'}")
    print("- allowed path set:")
    if allowed_paths:
        for p in allowed_paths:
            print(f"  - {p}")
    else:
        print("  - (none)")

    if guard_messages:
        print("- guard messages:")
        for msg in guard_messages:
            print(f"  - {msg}")

    guard_decision = guard_report.get("decision", "pass")
    guard_reason = guard_report.get("decision_reason", "n/a")
    print(f"- guard decision: {guard_decision}")
    print(f"- decision reason: {guard_reason}")
    print(f"- advisory report: {GUARD_REPORT_REL_PATH}")

    generated_paths: Dict[str, Optional[str]] = {
        "move_plan_md": None,
        "move_plan_sh": None,
        "rollback_plan_md": None,
        "rollback_plan_sh": None,
    }
    plan_messages: List[str] = []
    plan_ok = True

    if generate_plans:
        plan_ok, plan_messages, generated_paths = run_rollback_helper_for_debug_guard(
            repo_root=repo_root,
            output_dir=output_dir,
            report_rel_path=GUARD_REPORT_REL_PATH,
            module_path=effective_module_path,
            only_violations=only_violations,
            plans=plans,
        )
        if not plan_ok:
            print("- plan generation: failed", file=sys.stderr)
            for msg in plan_messages:
                print(f"  - {msg}", file=sys.stderr)
        else:
            print("- plan generation: completed")

    if generated_paths["move_plan_md"]:
        print(f"- move_plan.md: {generated_paths['move_plan_md']}")
        if generated_paths["move_plan_sh"]:
            print(f"- move_plan.sh: {generated_paths['move_plan_sh']}")
        else:
            print("- move_plan.sh: not generated (module-path unavailable or no move targets)")
    elif plans in {"move", "both"} and generate_plans:
        print("- move_plan.md: not generated")
        if effective_module_path is None:
            print("- hint: 要生成 move_plan 需提供 -m/--module-path")

    if generated_paths["rollback_plan_md"]:
        print(f"- rollback_plan.md: {generated_paths['rollback_plan_md']}")
        if generated_paths["rollback_plan_sh"]:
            print(f"- rollback_plan.sh: {generated_paths['rollback_plan_sh']}")
    elif plans in {"rollback", "both"} and generate_plans:
        print("- rollback_plan.md: not generated")

    if not generate_plans:
        print("- plan generation: skipped (--generate-plans=false)")

    # debug-guard is advisory by design; only usage/path errors above should return non-zero.
    return 0


def cmd_apply_move(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)
    policy, _policy_sources, policy_cli = load_effective_policy(args, repo_root)
    policy_cli_args = policy_subprocess_args(policy_cli)

    context_id = args.context_id or f"ctx-{uuid4().hex[:12]}"
    trace_id = args.trace_id or f"trace-{uuid4().hex}"

    try:
        output_dir = resolve_output_dir_under_tools(args.output_dir, repo_root, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    report_arg = args.report
    if (
        report_arg == GUARD_REPORT_REL_PATH
        and output_dir.resolve() != paths["tools_dir"].resolve()
    ):
        report_arg = str(to_repo_relative(output_dir / "guard_report.json", repo_root))

    try:
        report_path = resolve_report_path_under_output_dir(
            repo_root=repo_root,
            tools_dir=paths["tools_dir"],
            output_dir=output_dir,
            report_arg=report_arg,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    only_violations = parse_cli_bool(args.only_violations, default=True)
    move_dry_run = parse_cli_bool(args.move_dry_run, default=True)
    recheck = parse_cli_bool(args.recheck, default=True)
    verify_gate_default = parse_cli_bool(
        get_policy_value(policy, "gates.verify_gate.enabled", True), default=True
    )
    verify_gate_enabled = parse_cli_bool(args.verify_gate, default=verify_gate_default)
    verify_threshold = str(args.verify_threshold).strip().upper()
    verify_refresh = parse_cli_bool(args.verify_refresh, default=False)
    if verify_threshold not in {"PASS", "WARN", "FAIL"}:
        print(f"Invalid --verify-threshold: {args.verify_threshold}", file=sys.stderr)
        return 2
    snapshot_enabled_default = parse_cli_bool(
        get_policy_value(policy, "snapshots.enabled_on_apply", True), default=True
    )
    snapshot_enabled = parse_cli_bool(getattr(args, "snapshot", ""), default=snapshot_enabled_default)
    snapshot_max_copy_mb = parse_int_arg(
        get_policy_value(policy, "snapshots.max_copy_size_mb", 20), default=20, minimum=1
    )
    if bool(getattr(args, "no_snapshot", False)):
        snapshot_enabled = False
    snapshot_label = str(getattr(args, "snapshot_label", "") or "").strip() or "apply-move"
    snapshot_created = False
    snapshot_path: Optional[str] = None
    snapshot_label_for_trace: Optional[str] = snapshot_label if snapshot_enabled else None
    snapshot_dir = (paths["tools_dir"] / "snapshots").resolve()
    if snapshot_enabled:
        try:
            snapshot_dir = resolve_output_dir_under_tools(
                str(getattr(args, "snapshot_dir", "") or "").strip()
                or str(get_policy_value(policy, "paths.snapshots_dir", "prompt-dsl-system/tools/snapshots")),
                repo_root,
                paths["tools_dir"],
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.module_path:
        try:
            effective_module_path, module_path_source = resolve_effective_module_path(
                args.module_path, repo_root, None
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    else:
        effective_module_path, module_path_source = try_module_path_from_report(repo_root, report_path)
        if effective_module_path is None:
            default_report = (repo_root / GUARD_REPORT_REL_PATH).resolve()
            if default_report != report_path:
                derived_module, derived_source = try_module_path_from_report(repo_root, default_report)
                if derived_module is not None:
                    effective_module_path = derived_module
                    module_path_source = derived_source

    verify_report_path = Path(args.verify_report)
    if not verify_report_path.is_absolute():
        verify_report_path = (repo_root / verify_report_path).resolve()
    else:
        verify_report_path = verify_report_path.resolve()
    try:
        ensure_output_under_tools(verify_report_path, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    ack_used = normalize_ack_used(
        ack_source=getattr(args, "ack_source", None),
        ack=args.ack,
        ack_file=getattr(args, "ack_file", None),
        ack_latest=bool(getattr(args, "ack_latest", False)),
    )
    release_gate_ack, ack_err = resolve_ack_token(
        repo_root=repo_root,
        output_dir=output_dir,
        ack=args.ack,
        ack_file=getattr(args, "ack_file", None),
        ack_latest=bool(getattr(args, "ack_latest", False)),
    )
    if ack_err:
        print(f"[apply-move][error] {ack_err}", file=sys.stderr)
        return 2
    if release_gate_ack is None:
        ack_used = "none"
    elif ack_used == "none":
        ack_used = "ack"

    verify_trace_state = parse_verify_from_gate_report(
        gate_report={},
        verify_report_path=verify_report_path,
        verify_gate_enabled=verify_gate_enabled,
        verify_threshold=verify_threshold,
    )
    guard_report: Dict[str, Any] = {}

    def write_trace(action: str, blocked_by: str, exit_code: int) -> None:
        record = build_trace_record(
            repo_root=repo_root,
            context_id=context_id,
            trace_id=trace_id,
            command="apply-move",
            pipeline_path=None,
            effective_module_path=effective_module_path,
            module_path_source=module_path_source,
            guard_report=guard_report,
            action=action,
            verify_status=verify_trace_state["verify_status"],
            verify_hits_total=verify_trace_state["verify_hits_total"],
            verify_gate_required=verify_trace_state["verify_gate_required"],
            verify_gate_triggered=verify_trace_state["verify_gate_triggered"],
            ack_used=ack_used,
            blocked_by=blocked_by,
            exit_code=exit_code,
            snapshot_created=snapshot_created,
            snapshot_path=snapshot_path,
            snapshot_label=snapshot_label_for_trace,
        )
        try:
            append_trace_history(repo_root, record)
        except OSError as exc:
            print(f"[WARN] failed to append trace history: {exc}", file=sys.stderr)

    print("apply-move: precheck (debug-guard advisory + plans)")
    guard_ok, guard_messages, _guard_report = run_path_diff_guard(
        repo_root=repo_root,
        mode="debug-guard",
        module_path=effective_module_path,
        module_path_source=module_path_source,
        advisory=True,
    )
    if not guard_ok:
        for msg in guard_messages:
            print(msg, file=sys.stderr)
        guard_report = read_guard_report(repo_root)
        write_trace(action="blocked", blocked_by="guard_gate", exit_code=2)
        return 2

    default_report_path = (repo_root / GUARD_REPORT_REL_PATH).resolve()
    copy_guard_report(default_report_path, report_path)

    plan_ok, plan_messages, _pre_paths = run_rollback_helper_for_debug_guard(
        repo_root=repo_root,
        output_dir=output_dir,
        report_rel_path=to_repo_relative(report_path, repo_root),
        module_path=effective_module_path,
        only_violations=only_violations,
        plans="both",
    )
    if not plan_ok:
        print("[apply-move][error] failed to generate plans during precheck", file=sys.stderr)
        for msg in plan_messages:
            print(f"- {msg}", file=sys.stderr)
        guard_report = read_guard_report(repo_root, report_path=report_path)
        write_trace(action="blocked", blocked_by="none", exit_code=2)
        return 2

    guard_report = read_guard_report(repo_root, report_path=report_path)
    decision = str(guard_report.get("decision", "pass"))
    reason = str(guard_report.get("decision_reason", "n/a"))
    print(f"apply-move: guard decision={decision} reason={reason}")
    print(f"apply-move: report={to_repo_relative(report_path, repo_root)}")

    if decision == "pass":
        print("no violations, nothing to move")
        write_trace(action="completed", blocked_by="none", exit_code=0)
        return 0

    move_report_path = (output_dir / "move_report.json").resolve()
    move_report = read_json_dict(move_report_path)
    move_total, move_non_movable, move_high_risk = extract_move_report_summary(move_report)
    dst_conflict = has_dst_exists_conflict(move_report)

    if not (move_non_movable == 0 and move_high_risk == 0):
        if dst_conflict:
            print("Move conflicts detected", file=sys.stderr)
            resolver_ok, resolver_rc, resolver_msgs, resolver_paths = run_move_conflict_resolver(
                repo_root=repo_root,
                output_dir=output_dir,
                module_path=effective_module_path,
                mode="plan",
                strategy="abort",
                yes=False,
                dry_run=True,
                risk_threshold="HIGH",
            )
            for msg in resolver_msgs:
                print(f"[apply-move][conflict] {msg}", file=sys.stderr)
            if resolver_paths.get("conflict_plan_md"):
                print(f"conflict plan: {resolver_paths['conflict_plan_md']}", file=sys.stderr)
            else:
                print(
                    f"conflict plan: {to_repo_relative(output_dir / 'conflict_plan.md', repo_root)}",
                    file=sys.stderr,
                )
            print(
                "./prompt-dsl-system/tools/run.sh resolve-move-conflicts -r . -m <MODULE_PATH> --strategy rename_suffix",
                file=sys.stderr,
            )
            exit_code = 2 if resolver_rc == 0 else resolver_rc
            write_trace(action="blocked", blocked_by="none", exit_code=exit_code)
            return exit_code

        print("[apply-move][error] move plan contains non-movable high-risk items", file=sys.stderr)
        print(f"- move_report: {to_repo_relative(move_report_path, repo_root)}", file=sys.stderr)
        print(
            f"- summary: total={move_total}, non_movable={move_non_movable}, high_risk={move_high_risk}",
            file=sys.stderr,
        )
        print("Review move_plan.md and resolve blockers manually before applying moves.", file=sys.stderr)
        write_trace(action="blocked", blocked_by="none", exit_code=2)
        return 2

    wants_real_apply = bool(args.yes) and not move_dry_run
    if wants_real_apply and verify_gate_enabled:
        release_gate_ok, release_gate_code, release_gate_report, release_gate_messages = ensure_release_gate(
            repo_root=repo_root,
            command_name="apply-move",
            module_path=effective_module_path,
            module_path_source=module_path_source,
            output_dir=output_dir,
            guard_report_path=report_path,
            loop_report_path=(output_dir / "loop_diagnostics.json").resolve(),
            move_report_path=move_report_path,
            ack=release_gate_ack,
            verify_gate_enabled=verify_gate_enabled,
            verify_threshold=verify_threshold,
            verify_report_path=verify_report_path,
            verify_refresh=verify_refresh,
            risk_gate_enabled=False,
            risk_threshold="HIGH",
            risk_ttl_minutes=30,
            risk_exit_code=4,
            token_out=(output_dir / "RISK_GATE_TOKEN.txt").resolve(),
            token_json_out=(output_dir / "RISK_GATE_TOKEN.json").resolve(),
            json_out=(output_dir / "risk_gate_report.json").resolve(),
            consume_on_pass=False,
            policy_cli_args=policy_cli_args,
        )
        for msg in release_gate_messages:
            print(f"[apply-move][warn] {msg}", file=sys.stderr)
        verify_trace_state = parse_verify_from_gate_report(
            release_gate_report,
            verify_report_path=verify_report_path,
            verify_gate_enabled=verify_gate_enabled,
            verify_threshold=verify_threshold,
        )
        if not release_gate_ok:
            overall_risk = str(release_gate_report.get("overall_risk", "unknown"))
            token_rel = to_repo_relative((output_dir / "RISK_GATE_TOKEN.txt").resolve(), repo_root)
            next_cmd = release_gate_report.get("next_cmd")
            if not isinstance(next_cmd, str) or not next_cmd.strip():
                next_cmd = "./prompt-dsl-system/tools/run.sh apply-move -r . -m <MODULE_PATH> --yes --move-dry-run false --ack-latest"
            print(
                f"[release-gate] blocked before apply-move execution: overall_risk={overall_risk}",
                file=sys.stderr,
            )
            print(f"[release-gate] token file: {token_rel}", file=sys.stderr)
            print(f"NEXT_CMD: {next_cmd}", file=sys.stderr)
            write_trace(
                action="blocked",
                blocked_by=detect_blocked_by_from_gate_report(release_gate_report),
                exit_code=release_gate_code if release_gate_code > 0 else 4,
            )
            append_ack_note(
                repo_root=repo_root,
                command="apply-move",
                context_id=context_id,
                trace_id=trace_id,
                note=getattr(args, "ack_note", None),
                verify_status=verify_trace_state["verify_status"],
                verify_hits_total=verify_trace_state["verify_hits_total"],
                ack_used=ack_used,
            )
            return release_gate_code if release_gate_code > 0 else 4

    if wants_real_apply:
        if snapshot_enabled:
            snapshot_ok, snapshot_messages, snapshot_outputs = run_snapshot_manager(
                repo_root=repo_root,
                snapshot_dir=snapshot_dir,
                context_id=context_id,
                trace_id=trace_id,
                label=snapshot_label,
                includes=[
                    report_path,
                    move_report_path,
                    verify_report_path,
                    (output_dir / "risk_gate_report.json").resolve(),
                    (output_dir / "RISK_GATE_TOKEN.json").resolve(),
                    (output_dir / "conflict_plan.json").resolve(),
                ],
                max_copy_size_mb=snapshot_max_copy_mb,
                policy_cli_args=policy_cli_args,
            )
            for msg in snapshot_messages:
                print(f"[apply-move][snapshot] {msg}", file=sys.stderr)
            if not snapshot_ok:
                print("[apply-move][error] snapshot creation failed; blocked to avoid apply without restore point.", file=sys.stderr)
                write_trace(action="blocked", blocked_by="none", exit_code=2)
                return 2
            snapshot_created = True
            snapshot_path = snapshot_outputs.get("snapshot_path")
            manifest_path = snapshot_outputs.get("manifest_json")
            if snapshot_path:
                print(f"apply-move: snapshot={snapshot_path}")
            if manifest_path:
                print(f"apply-move: snapshot_manifest={manifest_path}")
        else:
            snapshot_label_for_trace = None
            print("[apply-move][WARN] snapshot disabled by --no-snapshot", file=sys.stderr)

    apply_ok, apply_messages, apply_paths = run_rollback_helper_for_debug_guard(
        repo_root=repo_root,
        output_dir=output_dir,
        report_rel_path=to_repo_relative(report_path, repo_root),
        module_path=effective_module_path,
        only_violations=only_violations,
        plans="both",
        apply_move=False,
        move_dry_run=move_dry_run,
        yes=bool(args.yes),
        plan_only=False,
        move_mode_apply=True,
    )
    if not apply_ok:
        print("[apply-move][error] move apply was not executed or failed", file=sys.stderr)
        for msg in apply_messages:
            print(f"- {msg}", file=sys.stderr)
        if not args.yes or move_dry_run:
            print(
                "Confirmation required: rerun with --yes --move-dry-run false to execute file moves.",
                file=sys.stderr,
            )
        print(
            f"Plans are available at {to_repo_relative(output_dir, repo_root)} "
            "(move_plan / rollback_plan).",
            file=sys.stderr,
        )
        write_trace(action="blocked", blocked_by="none", exit_code=2)
        return 2

    if apply_paths.get("move_apply_log_md"):
        print(f"apply-move: move_apply_log={apply_paths['move_apply_log_md']}")

    if not recheck:
        print("move applied; recheck skipped (--recheck=false)")
        print("Next: ./prompt-dsl-system/tools/run.sh validate -r . -m <MODULE_PATH>")
        print("Next: ./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE>")
        write_trace(action="completed", blocked_by="none", exit_code=0)
        append_ack_note(
            repo_root=repo_root,
            command="apply-move",
            context_id=context_id,
            trace_id=trace_id,
            note=getattr(args, "ack_note", None),
            verify_status=verify_trace_state["verify_status"],
            verify_hits_total=verify_trace_state["verify_hits_total"],
            ack_used=ack_used,
        )
        return 0

    print("apply-move: recheck (debug-guard advisory + plans)")
    guard_ok2, guard_messages2, _guard_report2 = run_path_diff_guard(
        repo_root=repo_root,
        mode="debug-guard",
        module_path=effective_module_path,
        module_path_source=module_path_source,
        advisory=True,
    )
    if not guard_ok2:
        for msg in guard_messages2:
            print(msg, file=sys.stderr)
        write_trace(action="blocked", blocked_by="guard_gate", exit_code=2)
        return 2

    copy_guard_report(default_report_path, report_path)
    plan_ok2, plan_messages2, post_paths = run_rollback_helper_for_debug_guard(
        repo_root=repo_root,
        output_dir=output_dir,
        report_rel_path=to_repo_relative(report_path, repo_root),
        module_path=effective_module_path,
        only_violations=only_violations,
        plans="both",
    )
    if not plan_ok2:
        print("[apply-move][error] failed to refresh plans during recheck", file=sys.stderr)
        for msg in plan_messages2:
            print(f"- {msg}", file=sys.stderr)
        write_trace(action="blocked", blocked_by="none", exit_code=2)
        return 2

    report_after = read_guard_report(repo_root, report_path=report_path)
    decision_after = str(report_after.get("decision", "pass"))
    reason_after = str(report_after.get("decision_reason", "n/a"))
    if decision_after != "pass":
        rollback_hint = post_paths.get("rollback_plan_sh") or to_repo_relative(output_dir / "rollback_plan.sh", repo_root)
        print("move did not fully resolve violations", file=sys.stderr)
        print(f"recheck decision: {decision_after} ({reason_after})", file=sys.stderr)
        print(f"use rollback plan: {rollback_hint}", file=sys.stderr)
        guard_report = report_after
        write_trace(action="blocked", blocked_by="guard_gate", exit_code=2)
        return 2

    print("move resolved violations")
    print("Next: ./prompt-dsl-system/tools/run.sh validate -r . -m <MODULE_PATH>")
    print("Next: ./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE>")
    guard_report = report_after
    write_trace(action="completed", blocked_by="none", exit_code=0)
    append_ack_note(
        repo_root=repo_root,
        command="apply-move",
        context_id=context_id,
        trace_id=trace_id,
        note=getattr(args, "ack_note", None),
        verify_status=verify_trace_state["verify_status"],
        verify_hits_total=verify_trace_state["verify_hits_total"],
        ack_used=ack_used,
    )
    return 0


def cmd_resolve_move_conflicts(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)
    policy, _policy_sources, policy_cli = load_effective_policy(args, repo_root)
    policy_cli_args = policy_subprocess_args(policy_cli)

    context_id = args.context_id or f"ctx-{uuid4().hex[:12]}"
    trace_id = args.trace_id or f"trace-{uuid4().hex}"

    try:
        output_dir = resolve_output_dir_under_tools(args.output_dir, repo_root, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        effective_module_path, _module_path_source = resolve_effective_module_path(
            args.module_path, repo_root, None
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if effective_module_path is None:
        print("module-path is required for resolve-move-conflicts", file=sys.stderr)
        return 2

    mode = str(args.mode).strip().lower()
    strategy = str(args.strategy).strip().lower()
    if mode not in {"plan", "apply"}:
        print(f"Invalid mode: {args.mode}", file=sys.stderr)
        return 2
    if strategy not in {"rename_suffix", "imports_bucket", "abort"}:
        print(f"Invalid strategy: {args.strategy}", file=sys.stderr)
        return 2

    dry_run = parse_cli_bool(args.dry_run, default=True)
    snapshot_enabled_default = parse_cli_bool(
        get_policy_value(policy, "snapshots.enabled_on_apply", True), default=True
    )
    snapshot_enabled = parse_cli_bool(getattr(args, "snapshot", ""), default=snapshot_enabled_default)
    snapshot_max_copy_mb = parse_int_arg(
        get_policy_value(policy, "snapshots.max_copy_size_mb", 20), default=20, minimum=1
    )
    if bool(getattr(args, "no_snapshot", False)):
        snapshot_enabled = False
    snapshot_label = str(getattr(args, "snapshot_label", "") or "").strip() or "resolve-move-conflicts"
    snapshot_created = False
    snapshot_path: Optional[str] = None
    snapshot_label_for_trace: Optional[str] = snapshot_label if snapshot_enabled else None
    snapshot_dir = (paths["tools_dir"] / "snapshots").resolve()
    if snapshot_enabled:
        try:
            snapshot_dir = resolve_output_dir_under_tools(
                str(getattr(args, "snapshot_dir", "") or "").strip()
                or str(get_policy_value(policy, "paths.snapshots_dir", "prompt-dsl-system/tools/snapshots")),
                repo_root,
                paths["tools_dir"],
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    ack_used = normalize_ack_used(
        ack_source=getattr(args, "ack_source", None),
        ack=args.ack,
        ack_file=args.ack_file,
        ack_latest=bool(args.ack_latest),
    )
    if ack_used == "none" and (
        (isinstance(args.ack, str) and args.ack.strip())
        or (isinstance(args.ack_file, str) and args.ack_file.strip())
        or bool(args.ack_latest)
    ):
        ack_used = "ack"

    verify_status, verify_hits_total = parse_verify_snapshot((output_dir / "followup_verify_report.json").resolve())

    guard_report_path = (output_dir / "guard_report.json").resolve()
    guard_report = read_guard_report(repo_root, report_path=guard_report_path)

    def write_trace(action: str, blocked_by: str, exit_code: int) -> None:
        record = build_trace_record(
            repo_root=repo_root,
            context_id=context_id,
            trace_id=trace_id,
            command="resolve-move-conflicts",
            pipeline_path=None,
            effective_module_path=effective_module_path,
            module_path_source="cli",
            guard_report=guard_report,
            action=action,
            verify_status=verify_status,
            verify_hits_total=verify_hits_total,
            verify_gate_required=False,
            verify_gate_triggered=False,
            ack_used=ack_used,
            blocked_by=blocked_by,
            exit_code=exit_code,
            snapshot_created=snapshot_created,
            snapshot_path=snapshot_path,
            snapshot_label=snapshot_label_for_trace,
        )
        try:
            append_trace_history(repo_root, record)
        except OSError as exc:
            print(f"[WARN] failed to append trace history: {exc}", file=sys.stderr)

    wants_real_apply = mode == "apply" and bool(args.yes) and not dry_run
    if wants_real_apply:
        if snapshot_enabled:
            snapshot_ok, snapshot_messages, snapshot_outputs = run_snapshot_manager(
                repo_root=repo_root,
                snapshot_dir=snapshot_dir,
                context_id=context_id,
                trace_id=trace_id,
                label=snapshot_label,
                includes=[
                    (output_dir / "guard_report.json").resolve(),
                    (output_dir / "move_report.json").resolve(),
                    (output_dir / "conflict_plan.json").resolve(),
                    (output_dir / "risk_gate_report.json").resolve(),
                    (output_dir / "RISK_GATE_TOKEN.json").resolve(),
                    (output_dir / "followup_verify_report.json").resolve(),
                ],
                max_copy_size_mb=snapshot_max_copy_mb,
                policy_cli_args=policy_cli_args,
            )
            for msg in snapshot_messages:
                print(f"[resolve-move-conflicts][snapshot] {msg}", file=sys.stderr)
            if not snapshot_ok:
                print(
                    "[resolve-move-conflicts][error] snapshot creation failed; blocked to avoid apply without restore point.",
                    file=sys.stderr,
                )
                write_trace(action="blocked", blocked_by="none", exit_code=2)
                return 2
            snapshot_created = True
            snapshot_path = snapshot_outputs.get("snapshot_path")
            manifest_path = snapshot_outputs.get("manifest_json")
            if snapshot_path:
                print(f"resolve-move-conflicts: snapshot={snapshot_path}")
            if manifest_path:
                print(f"resolve-move-conflicts: snapshot_manifest={manifest_path}")
        else:
            snapshot_label_for_trace = None
            print("[resolve-move-conflicts][WARN] snapshot disabled by --no-snapshot", file=sys.stderr)

    ok, code, messages, produced = run_move_conflict_resolver(
        repo_root=repo_root,
        output_dir=output_dir,
        module_path=effective_module_path,
        mode=mode,
        strategy=strategy,
        yes=bool(args.yes),
        dry_run=dry_run,
        ack=args.ack,
        ack_file=args.ack_file,
        ack_latest=bool(args.ack_latest),
        risk_threshold=str(args.risk_threshold).upper(),
    )
    for msg in messages:
        print(f"[resolve-move-conflicts] {msg}", file=sys.stderr)

    if produced.get("conflict_plan_md"):
        print(f"conflict_plan: {produced['conflict_plan_md']}")
    if produced.get("rename_script"):
        print(f"rename_suffix_script: {produced['rename_script']}")
    if produced.get("imports_script"):
        print(f"imports_bucket_script: {produced['imports_script']}")
    if produced.get("abort_script"):
        print(f"abort_script: {produced['abort_script']}")
    if produced.get("conflict_apply_log_md"):
        print(f"conflict_apply_log: {produced['conflict_apply_log_md']}")
    if produced.get("followup_checklist_rename"):
        print(f"followup_checklist_rename: {produced['followup_checklist_rename']}")
    if produced.get("followup_checklist_imports"):
        print(f"followup_checklist_imports: {produced['followup_checklist_imports']}")
    if produced.get("followup_checklist_abort"):
        print(f"followup_checklist_abort: {produced['followup_checklist_abort']}")
    if produced.get("followup_checklist_after_apply"):
        print(f"followup_checklist_after_apply: {produced['followup_checklist_after_apply']}")

    if not ok:
        exit_code = code if code > 0 else 2
        blocked_by = "risk_gate" if exit_code == 4 else "none"
        write_trace(action="blocked", blocked_by=blocked_by, exit_code=exit_code)
        return exit_code

    if mode == "apply":
        print("Next: ./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH>")
        print("Next: ./prompt-dsl-system/tools/run.sh validate -r .")
    write_trace(action="completed", blocked_by="none", exit_code=0)
    return 0


def cmd_scan_followup(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)

    try:
        output_dir = resolve_output_dir_under_tools(args.output_dir, repo_root, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    moves_arg = str(args.moves or "").strip()
    if not moves_arg:
        print("--moves is required", file=sys.stderr)
        return 2
    moves_path = Path(moves_arg)
    if not moves_path.is_absolute():
        moves_path = (repo_root / moves_path).resolve()
    if not moves_path.exists() or not moves_path.is_file():
        print(f"moves file not found: {moves_path}", file=sys.stderr)
        return 2

    mode = str(args.mode).strip().lower()
    if mode not in {"plan", "apply"}:
        print(f"Invalid --mode: {args.mode}", file=sys.stderr)
        return 2
    max_hits = parse_int_arg(args.max_hits_per_move, default=50, minimum=1)

    ok, code, messages, produced = run_ref_followup_scanner(
        repo_root=repo_root,
        moves_path=moves_path,
        output_dir=output_dir,
        mode=mode,
        max_hits_per_move=max_hits,
    )
    for msg in messages:
        print(f"[scan-followup] {msg}", file=sys.stderr)

    if produced.get("followup_checklist"):
        print(f"followup_checklist: {produced['followup_checklist']}")
    if produced.get("followup_scan_report"):
        print(f"followup_scan_report: {produced['followup_scan_report']}")

    return 0 if ok else (code if code > 0 else 2)


def cmd_apply_followup_fixes(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)
    policy, _policy_sources, policy_cli = load_effective_policy(args, repo_root)
    policy_cli_args = policy_subprocess_args(policy_cli)

    context_id = args.context_id or f"ctx-{uuid4().hex[:12]}"
    trace_id = args.trace_id or f"trace-{uuid4().hex}"

    try:
        output_dir = resolve_output_dir_under_tools(args.output_dir, repo_root, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    scan_arg = str(args.scan_report or "").strip()
    if not scan_arg:
        print("--scan-report is required", file=sys.stderr)
        return 2
    scan_path = Path(scan_arg)
    if not scan_path.is_absolute():
        scan_path = (repo_root / scan_path).resolve()
    if not scan_path.exists() or not scan_path.is_file():
        print(f"scan report not found: {scan_path}", file=sys.stderr)
        return 2

    mode = str(args.mode).strip().lower()
    if mode not in {"plan", "apply"}:
        print(f"Invalid --mode: {args.mode}", file=sys.stderr)
        return 2
    dry_run = parse_cli_bool(args.dry_run, default=True)
    verify_gate_default = parse_cli_bool(
        get_policy_value(policy, "gates.verify_gate.enabled", True), default=True
    )
    verify_gate_enabled = parse_cli_bool(args.verify_gate, default=verify_gate_default)
    verify_threshold = str(args.verify_threshold).strip().upper()
    verify_refresh = parse_cli_bool(args.verify_refresh, default=False)
    if verify_threshold not in {"PASS", "WARN", "FAIL"}:
        print(f"Invalid --verify-threshold: {args.verify_threshold}", file=sys.stderr)
        return 2
    max_changes = parse_int_arg(args.max_changes, default=100, minimum=1)
    threshold = str(args.confidence_threshold).strip().lower()
    if threshold not in {"low", "medium", "high"}:
        print(f"Invalid --confidence-threshold: {args.confidence_threshold}", file=sys.stderr)
        return 2
    snapshot_enabled_default = parse_cli_bool(
        get_policy_value(policy, "snapshots.enabled_on_apply", True), default=True
    )
    snapshot_enabled = parse_cli_bool(getattr(args, "snapshot", ""), default=snapshot_enabled_default)
    snapshot_max_copy_mb = parse_int_arg(
        get_policy_value(policy, "snapshots.max_copy_size_mb", 20), default=20, minimum=1
    )
    if bool(getattr(args, "no_snapshot", False)):
        snapshot_enabled = False
    snapshot_label = str(getattr(args, "snapshot_label", "") or "").strip() or "apply-followup-fixes"
    snapshot_created = False
    snapshot_path: Optional[str] = None
    snapshot_label_for_trace: Optional[str] = snapshot_label if snapshot_enabled else None
    snapshot_dir = (paths["tools_dir"] / "snapshots").resolve()
    if snapshot_enabled:
        try:
            snapshot_dir = resolve_output_dir_under_tools(
                str(getattr(args, "snapshot_dir", "") or "").strip()
                or str(get_policy_value(policy, "paths.snapshots_dir", "prompt-dsl-system/tools/snapshots")),
                repo_root,
                paths["tools_dir"],
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    include_ext = list(args.include_ext) if isinstance(args.include_ext, list) else []
    exclude_path = list(args.exclude_path) if isinstance(args.exclude_path, list) else []

    verify_report_path = Path(args.verify_report)
    if not verify_report_path.is_absolute():
        verify_report_path = (repo_root / verify_report_path).resolve()
    else:
        verify_report_path = verify_report_path.resolve()
    try:
        ensure_output_under_tools(verify_report_path, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    effective_module_path: Optional[Path] = None
    module_path_source = "none"
    if args.module_path:
        try:
            effective_module_path, module_path_source = resolve_effective_module_path(
                args.module_path, repo_root, None
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    ack_used = normalize_ack_used(
        ack_source=getattr(args, "ack_source", None),
        ack=args.ack,
        ack_file=getattr(args, "ack_file", None),
        ack_latest=bool(getattr(args, "ack_latest", False)),
    )
    release_gate_ack, ack_err = resolve_ack_token(
        repo_root=repo_root,
        output_dir=output_dir,
        ack=args.ack,
        ack_file=args.ack_file,
        ack_latest=bool(args.ack_latest),
    )
    if ack_err:
        print(f"[apply-followup-fixes][error] {ack_err}", file=sys.stderr)
        return 2
    if release_gate_ack is None:
        ack_used = "none"
    elif ack_used == "none":
        ack_used = "ack"

    verify_trace_state = parse_verify_from_gate_report(
        gate_report={},
        verify_report_path=verify_report_path,
        verify_gate_enabled=verify_gate_enabled,
        verify_threshold=verify_threshold,
    )

    def write_trace(action: str, blocked_by: str, exit_code: int) -> None:
        record = build_trace_record(
            repo_root=repo_root,
            context_id=context_id,
            trace_id=trace_id,
            command="apply-followup-fixes",
            pipeline_path=None,
            effective_module_path=effective_module_path,
            module_path_source=module_path_source,
            guard_report={},
            action=action,
            verify_status=verify_trace_state["verify_status"],
            verify_hits_total=verify_trace_state["verify_hits_total"],
            verify_gate_required=verify_trace_state["verify_gate_required"],
            verify_gate_triggered=verify_trace_state["verify_gate_triggered"],
            ack_used=ack_used,
            blocked_by=blocked_by,
            exit_code=exit_code,
            snapshot_created=snapshot_created,
            snapshot_path=snapshot_path,
            snapshot_label=snapshot_label_for_trace,
        )
        try:
            append_trace_history(repo_root, record)
        except OSError as exc:
            print(f"[WARN] failed to append trace history: {exc}", file=sys.stderr)

    wants_real_apply = mode == "apply" and bool(args.yes) and not dry_run
    if wants_real_apply and verify_gate_enabled:
        release_gate_ok, release_gate_code, release_gate_report, release_gate_messages = ensure_release_gate(
            repo_root=repo_root,
            command_name="apply-followup-fixes",
            module_path=effective_module_path,
            module_path_source=module_path_source,
            output_dir=output_dir,
            guard_report_path=(output_dir / "guard_report.json").resolve(),
            loop_report_path=(output_dir / "loop_diagnostics.json").resolve(),
            move_report_path=(output_dir / "move_report.json").resolve(),
            ack=release_gate_ack,
            verify_gate_enabled=verify_gate_enabled,
            verify_threshold=verify_threshold,
            verify_report_path=verify_report_path,
            verify_refresh=verify_refresh,
            risk_gate_enabled=False,
            risk_threshold="HIGH",
            risk_ttl_minutes=30,
            risk_exit_code=4,
            token_out=(output_dir / "RISK_GATE_TOKEN.txt").resolve(),
            token_json_out=(output_dir / "RISK_GATE_TOKEN.json").resolve(),
            json_out=(output_dir / "risk_gate_report.json").resolve(),
            consume_on_pass=False,
            policy_cli_args=policy_cli_args,
        )
        for msg in release_gate_messages:
            print(f"[apply-followup-fixes][warn] {msg}", file=sys.stderr)
        verify_trace_state = parse_verify_from_gate_report(
            release_gate_report,
            verify_report_path=verify_report_path,
            verify_gate_enabled=verify_gate_enabled,
            verify_threshold=verify_threshold,
        )
        if not release_gate_ok:
            overall_risk = str(release_gate_report.get("overall_risk", "unknown"))
            token_rel = to_repo_relative((output_dir / "RISK_GATE_TOKEN.txt").resolve(), repo_root)
            next_cmd = release_gate_report.get("next_cmd")
            if not isinstance(next_cmd, str) or not next_cmd.strip():
                next_cmd = (
                    "./prompt-dsl-system/tools/run.sh apply-followup-fixes -r . "
                    "--scan-report <SCAN_REPORT> --mode apply --yes --dry-run false --ack-latest"
                )
            print(
                f"[release-gate] blocked before apply-followup-fixes execution: overall_risk={overall_risk}",
                file=sys.stderr,
            )
            print(f"[release-gate] token file: {token_rel}", file=sys.stderr)
            print(f"NEXT_CMD: {next_cmd}", file=sys.stderr)
            write_trace(
                action="blocked",
                blocked_by=detect_blocked_by_from_gate_report(release_gate_report),
                exit_code=release_gate_code if release_gate_code > 0 else 4,
            )
            append_ack_note(
                repo_root=repo_root,
                command="apply-followup-fixes",
                context_id=context_id,
                trace_id=trace_id,
                note=getattr(args, "ack_note", None),
                verify_status=verify_trace_state["verify_status"],
                verify_hits_total=verify_trace_state["verify_hits_total"],
                ack_used=ack_used,
            )
            return release_gate_code if release_gate_code > 0 else 4

    if wants_real_apply:
        if snapshot_enabled:
            snapshot_ok, snapshot_messages, snapshot_outputs = run_snapshot_manager(
                repo_root=repo_root,
                snapshot_dir=snapshot_dir,
                context_id=context_id,
                trace_id=trace_id,
                label=snapshot_label,
                includes=[
                    scan_path,
                    verify_report_path,
                    (output_dir / "followup_patch_plan.json").resolve(),
                    (output_dir / "followup_verify_report.json").resolve(),
                    (output_dir / "guard_report.json").resolve(),
                    (output_dir / "move_report.json").resolve(),
                    (output_dir / "risk_gate_report.json").resolve(),
                    (output_dir / "RISK_GATE_TOKEN.json").resolve(),
                ],
                max_copy_size_mb=snapshot_max_copy_mb,
                policy_cli_args=policy_cli_args,
            )
            for msg in snapshot_messages:
                print(f"[apply-followup-fixes][snapshot] {msg}", file=sys.stderr)
            if not snapshot_ok:
                print(
                    "[apply-followup-fixes][error] snapshot creation failed; blocked to avoid apply without restore point.",
                    file=sys.stderr,
                )
                write_trace(action="blocked", blocked_by="none", exit_code=2)
                return 2
            snapshot_created = True
            snapshot_path = snapshot_outputs.get("snapshot_path")
            manifest_path = snapshot_outputs.get("manifest_json")
            if snapshot_path:
                print(f"apply-followup-fixes: snapshot={snapshot_path}")
            if manifest_path:
                print(f"apply-followup-fixes: snapshot_manifest={manifest_path}")
        else:
            snapshot_label_for_trace = None
            print("[apply-followup-fixes][WARN] snapshot disabled by --no-snapshot", file=sys.stderr)

    ok, code, messages, produced = run_followup_patch_generator(
        repo_root=repo_root,
        scan_report_path=scan_path,
        output_dir=output_dir,
        mode=mode,
        yes=bool(args.yes),
        dry_run=dry_run,
        max_changes=max_changes,
        confidence_threshold=threshold,
        include_ext=include_ext,
        exclude_path=exclude_path,
        ack=args.ack,
        ack_file=args.ack_file,
        ack_latest=bool(args.ack_latest),
        risk_threshold=str(args.risk_threshold).upper(),
    )
    for msg in messages:
        print(f"[apply-followup-fixes] {msg}", file=sys.stderr)

    if produced.get("followup_patch_plan_json"):
        print(f"followup_patch_plan_json: {produced['followup_patch_plan_json']}")
    if produced.get("followup_patch_plan_md"):
        print(f"followup_patch_plan_md: {produced['followup_patch_plan_md']}")
    if produced.get("followup_patch_diff"):
        print(f"followup_patch_diff: {produced['followup_patch_diff']}")
    if produced.get("followup_patch_apply_log"):
        print(f"followup_patch_apply_log: {produced['followup_patch_apply_log']}")

    exit_code = 0 if ok else (code if code > 0 else 2)
    write_trace(action="completed" if exit_code == 0 else "blocked", blocked_by="none", exit_code=exit_code)
    append_ack_note(
        repo_root=repo_root,
        command="apply-followup-fixes",
        context_id=context_id,
        trace_id=trace_id,
        note=getattr(args, "ack_note", None),
        verify_status=verify_trace_state["verify_status"],
        verify_hits_total=verify_trace_state["verify_hits_total"],
        ack_used=ack_used,
    )
    return exit_code


def cmd_verify_followup_fixes(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)

    try:
        output_dir = resolve_output_dir_under_tools(args.output_dir, repo_root, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    moves_arg = str(args.moves or "").strip()
    if not moves_arg:
        print("--moves is required", file=sys.stderr)
        return 2
    moves_path = Path(moves_arg)
    if not moves_path.is_absolute():
        moves_path = (repo_root / moves_path).resolve()
    if not moves_path.exists() or not moves_path.is_file():
        print(f"moves file not found: {moves_path}", file=sys.stderr)
        return 2

    scan_report_path: Optional[Path] = None
    if str(args.scan_report or "").strip():
        scan_report_path = Path(str(args.scan_report).strip())
        if not scan_report_path.is_absolute():
            scan_report_path = (repo_root / scan_report_path).resolve()
        if not scan_report_path.exists() or not scan_report_path.is_file():
            print(f"scan report not found: {scan_report_path}", file=sys.stderr)
            return 2

    patch_plan_path: Optional[Path] = None
    if str(args.patch_plan or "").strip():
        patch_plan_path = Path(str(args.patch_plan).strip())
        if not patch_plan_path.is_absolute():
            patch_plan_path = (repo_root / patch_plan_path).resolve()
        if not patch_plan_path.exists() or not patch_plan_path.is_file():
            print(f"patch plan not found: {patch_plan_path}", file=sys.stderr)
            return 2

    mode = str(args.mode).strip().lower()
    if mode not in {"post-move", "post-patch", "full"}:
        print(f"Invalid --mode: {args.mode}", file=sys.stderr)
        return 2
    max_hits = parse_int_arg(args.max_hits, default=200, minimum=1)
    use_rg = parse_cli_bool(args.use_rg, default=True)
    include_ext = list(args.include_ext) if isinstance(args.include_ext, list) else []
    exclude_dir = list(args.exclude_dir) if isinstance(args.exclude_dir, list) else []

    ok, code, messages, produced = run_followup_verifier(
        repo_root=repo_root,
        moves_path=moves_path,
        output_dir=output_dir,
        mode=mode,
        scan_report=scan_report_path,
        patch_plan=patch_plan_path,
        max_hits=max_hits,
        use_rg=use_rg,
        include_ext=include_ext,
        exclude_dir=exclude_dir,
    )
    for msg in messages:
        print(f"[verify-followup-fixes] {msg}", file=sys.stderr)

    if produced.get("followup_verify_report_json"):
        print(f"followup_verify_report_json: {produced['followup_verify_report_json']}")
    if produced.get("followup_verify_report_md"):
        print(f"followup_verify_report_md: {produced['followup_verify_report_md']}")

    return 0 if ok else (code if code > 0 else 2)


def cmd_snapshot_restore_guide(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)

    snapshot_arg = str(args.snapshot or "").strip()
    if not snapshot_arg:
        print("--snapshot is required", file=sys.stderr)
        return 2
    snapshot_path = Path(snapshot_arg)
    if not snapshot_path.is_absolute():
        snapshot_path = (repo_root / snapshot_path).resolve()
    else:
        snapshot_path = snapshot_path.resolve()
    if not snapshot_path.exists() or not snapshot_path.is_dir():
        print(f"snapshot directory not found: {snapshot_path}", file=sys.stderr)
        return 2
    try:
        ensure_output_under_tools(snapshot_path, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir: Optional[Path]
    output_arg = str(getattr(args, "output_dir", "") or "").strip()
    if output_arg:
        try:
            output_dir = resolve_output_dir_under_tools(output_arg, repo_root, paths["tools_dir"])
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    else:
        output_dir = (snapshot_path / "restore").resolve()
        try:
            ensure_output_under_tools(output_dir, paths["tools_dir"])
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        output_dir.mkdir(parents=True, exist_ok=True)

    mode = str(args.mode).strip().lower()
    if mode not in {"generate", "check"}:
        print(f"Invalid --mode: {args.mode}", file=sys.stderr)
        return 2
    shell = str(args.shell).strip().lower()
    if shell not in {"bash", "zsh"}:
        print(f"Invalid --shell: {args.shell}", file=sys.stderr)
        return 2

    strict = parse_cli_bool(getattr(args, "strict", "true"), default=True)
    if bool(getattr(args, "no_strict", False)):
        strict = False
    dry_run = parse_cli_bool(getattr(args, "dry_run", "true"), default=True)

    ok, code, messages, produced = run_snapshot_restore_guide(
        repo_root=repo_root,
        snapshot_path=snapshot_path,
        output_dir=output_dir,
        shell=shell,
        mode=mode,
        strict=strict,
        dry_run=dry_run,
    )
    for msg in messages:
        print(f"[snapshot-restore-guide] {msg}", file=sys.stderr)

    if produced.get("restore_check_json"):
        print(f"restore_check_json: {produced['restore_check_json']}")
    if produced.get("restore_guide_md"):
        print(f"restore_guide_md: {produced['restore_guide_md']}")
    if produced.get("restore_full_sh"):
        print(f"restore_full_sh: {produced['restore_full_sh']}")
    if produced.get("restore_files_sh"):
        print(f"restore_files_sh: {produced['restore_files_sh']}")

    return 0 if ok else (code if code > 0 else 2)


def cmd_snapshot_prune(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)
    policy, _policy_sources, policy_cli = load_effective_policy(args, repo_root)
    policy_cli_args = policy_subprocess_args(policy_cli)

    snapshots_dir_default = str(get_policy_value(policy, "paths.snapshots_dir", "prompt-dsl-system/tools/snapshots") or "prompt-dsl-system/tools/snapshots")
    output_dir_default = str(get_policy_value(policy, "paths.tools_dir", "prompt-dsl-system/tools") or "prompt-dsl-system/tools")
    keep_last_default = parse_int_arg(get_policy_value(policy, "prune.keep_last", 20), default=20, minimum=0)
    max_size_default = parse_int_arg(get_policy_value(policy, "prune.max_total_size_mb", 1024), default=1024, minimum=1)
    dry_run_default = parse_cli_bool(get_policy_value(policy, "prune.dry_run_default", True), default=True)

    snapshots_dir_arg = str(getattr(args, "snapshots_dir", "") or "").strip() or snapshots_dir_default
    snapshots_dir = Path(snapshots_dir_arg)
    if not snapshots_dir.is_absolute():
        snapshots_dir = (repo_root / snapshots_dir).resolve()
    else:
        snapshots_dir = snapshots_dir.resolve()
    try:
        ensure_output_under_tools(snapshots_dir, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir_arg = str(getattr(args, "output_dir", "") or "").strip() or output_dir_default
    try:
        output_dir = resolve_output_dir_under_tools(output_dir_arg, repo_root, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    keep_last = parse_int_arg(getattr(args, "keep_last", ""), default=keep_last_default, minimum=0)
    max_total_size_mb = parse_int_arg(getattr(args, "max_total_size_mb", ""), default=max_size_default, minimum=1)
    dry_run = parse_cli_bool(getattr(args, "dry_run", ""), default=dry_run_default)
    apply_mode = bool(getattr(args, "apply", False))
    if apply_mode:
        dry_run = False

    only_labels = list(args.only_label) if isinstance(args.only_label, list) else []
    exclude_labels = list(args.exclude_label) if isinstance(args.exclude_label, list) else []
    now_iso_text = str(getattr(args, "now", "") or "").strip()

    ok, code, messages, produced = run_snapshot_prune(
        repo_root=repo_root,
        snapshots_dir=snapshots_dir,
        output_dir=output_dir,
        keep_last=keep_last,
        max_total_size_mb=max_total_size_mb,
        only_labels=only_labels,
        exclude_labels=exclude_labels,
        dry_run=dry_run,
        apply=apply_mode,
        now_iso_text=now_iso_text,
        policy_cli_args=policy_cli_args,
    )
    for msg in messages:
        print(f"[snapshot-prune] {msg}", file=sys.stderr)

    if produced.get("snapshot_prune_report_json"):
        print(f"snapshot_prune_report_json: {produced['snapshot_prune_report_json']}")
    if produced.get("snapshot_prune_report_md"):
        print(f"snapshot_prune_report_md: {produced['snapshot_prune_report_md']}")

    return 0 if ok else (code if code > 0 else 2)


def cmd_snapshot_index(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)
    policy, _policy_sources, policy_cli = load_effective_policy(args, repo_root)
    policy_cli_args = policy_subprocess_args(policy_cli)

    snapshots_dir_default = str(get_policy_value(policy, "paths.snapshots_dir", "prompt-dsl-system/tools/snapshots") or "prompt-dsl-system/tools/snapshots")
    output_dir_default = str(get_policy_value(policy, "paths.tools_dir", "prompt-dsl-system/tools") or "prompt-dsl-system/tools")
    limit_default = parse_int_arg(get_policy_value(policy, "index.snapshot_limit_md", 500), default=500, minimum=1)

    snapshots_dir_arg = str(getattr(args, "snapshots_dir", "") or "").strip() or snapshots_dir_default
    snapshots_dir = Path(snapshots_dir_arg)
    if not snapshots_dir.is_absolute():
        snapshots_dir = (repo_root / snapshots_dir).resolve()
    else:
        snapshots_dir = snapshots_dir.resolve()
    try:
        ensure_output_under_tools(snapshots_dir, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir_arg = str(getattr(args, "output_dir", "") or "").strip() or output_dir_default
    try:
        output_dir = resolve_output_dir_under_tools(output_dir_arg, repo_root, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    limit = parse_int_arg(getattr(args, "limit", ""), default=limit_default, minimum=1)
    include_invalid = parse_cli_bool(getattr(args, "include_invalid", "false"), default=False)
    now_iso_text = str(getattr(args, "now", "") or "").strip()

    ok, code, messages, produced = run_snapshot_indexer(
        repo_root=repo_root,
        snapshots_dir=snapshots_dir,
        output_dir=output_dir,
        limit=limit,
        include_invalid=include_invalid,
        now_iso_text=now_iso_text,
        policy_cli_args=policy_cli_args,
    )
    for msg in messages:
        print(f"[snapshot-index] {msg}", file=sys.stderr)
    if produced.get("snapshot_index_json"):
        print(f"snapshot_index_json: {produced['snapshot_index_json']}")
    if produced.get("snapshot_index_md"):
        print(f"snapshot_index_md: {produced['snapshot_index_md']}")

    return 0 if ok else (code if code > 0 else 2)


def cmd_snapshot_open(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)
    policy, _policy_sources, policy_cli = load_effective_policy(args, repo_root)
    policy_cli_args = policy_subprocess_args(policy_cli)

    index_default = str(get_policy_value(policy, "paths.snapshot_index_json", "prompt-dsl-system/tools/snapshot_index.json") or "prompt-dsl-system/tools/snapshot_index.json")
    snapshots_default = str(get_policy_value(policy, "paths.snapshots_dir", "prompt-dsl-system/tools/snapshots") or "prompt-dsl-system/tools/snapshots")

    index_arg = str(getattr(args, "index", "") or "").strip() or index_default
    index_path = Path(index_arg)
    if not index_path.is_absolute():
        index_path = (repo_root / index_path).resolve()
    else:
        index_path = index_path.resolve()
    try:
        ensure_output_under_tools(index_path, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    snapshots_dir_arg = str(getattr(args, "snapshots_dir", "") or "").strip() or snapshots_default
    snapshots_dir = Path(snapshots_dir_arg)
    if not snapshots_dir.is_absolute():
        snapshots_dir = (repo_root / snapshots_dir).resolve()
    else:
        snapshots_dir = snapshots_dir.resolve()
    try:
        ensure_output_under_tools(snapshots_dir, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_format = str(getattr(args, "output", "text")).strip().lower()
    if output_format not in {"json", "text", "md"}:
        print(f"Invalid --output: {args.output}", file=sys.stderr)
        return 2

    latest = parse_cli_bool(getattr(args, "latest", "true"), default=True)
    emit_restore_guide = parse_cli_bool(getattr(args, "emit_restore_guide", "false"), default=False)
    trace_id = str(getattr(args, "trace_id", "") or "").strip()
    snapshot_id = str(getattr(args, "snapshot_id", "") or "").strip()
    context_id = str(getattr(args, "context_id", "") or "").strip()
    label = str(getattr(args, "label", "") or "").strip()

    ok, code, messages, _out = run_snapshot_open(
        repo_root=repo_root,
        index_path=index_path,
        snapshots_dir=snapshots_dir,
        trace_id=trace_id,
        snapshot_id=snapshot_id,
        context_id=context_id,
        label=label,
        latest=latest,
        output_format=output_format,
        emit_restore_guide=emit_restore_guide,
        policy_cli_args=policy_cli_args,
    )
    for msg in messages:
        print(f"[snapshot-open] {msg}", file=sys.stderr)

    return 0 if ok else (code if code > 0 else 2)


def cmd_trace_index(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)
    policy, _policy_sources, policy_cli = load_effective_policy(args, repo_root)
    policy_cli_args = policy_subprocess_args(policy_cli)

    tools_dir_default = str(get_policy_value(policy, "paths.tools_dir", "prompt-dsl-system/tools") or "prompt-dsl-system/tools")
    trace_history_default = str(get_policy_value(policy, "paths.trace_history", f"{tools_dir_default}/trace_history.jsonl") or f"{tools_dir_default}/trace_history.jsonl")
    deliveries_default = str(get_policy_value(policy, "paths.deliveries_dir", f"{tools_dir_default}/deliveries") or f"{tools_dir_default}/deliveries")
    snapshots_default = str(get_policy_value(policy, "paths.snapshots_dir", f"{tools_dir_default}/snapshots") or f"{tools_dir_default}/snapshots")
    window_default = parse_int_arg(get_policy_value(policy, "index.trace_window", 200), default=200, minimum=1)
    scan_all_default = parse_cli_bool(get_policy_value(policy, "index.trace_scan_all", False), default=False)
    limit_md_default = parse_int_arg(get_policy_value(policy, "index.snapshot_limit_md", 200), default=200, minimum=1)

    tools_dir_arg = str(getattr(args, "tools_dir", "") or "").strip() or tools_dir_default
    tools_dir = Path(tools_dir_arg)
    if not tools_dir.is_absolute():
        tools_dir = (repo_root / tools_dir).resolve()
    else:
        tools_dir = tools_dir.resolve()
    try:
        ensure_output_under_tools(tools_dir, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    trace_history_arg = str(getattr(args, "trace_history", "") or "").strip() or trace_history_default
    trace_history = Path(trace_history_arg)
    if not trace_history.is_absolute():
        trace_history = (repo_root / trace_history).resolve()
    else:
        trace_history = trace_history.resolve()
    try:
        ensure_output_under_tools(trace_history, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    deliveries_arg = str(getattr(args, "deliveries_dir", "") or "").strip() or deliveries_default
    deliveries_dir = Path(deliveries_arg)
    if not deliveries_dir.is_absolute():
        deliveries_dir = (repo_root / deliveries_dir).resolve()
    else:
        deliveries_dir = deliveries_dir.resolve()
    try:
        ensure_output_under_tools(deliveries_dir, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    snapshots_arg = str(getattr(args, "snapshots_dir", "") or "").strip() or snapshots_default
    snapshots_dir = Path(snapshots_arg)
    if not snapshots_dir.is_absolute():
        snapshots_dir = (repo_root / snapshots_dir).resolve()
    else:
        snapshots_dir = snapshots_dir.resolve()
    try:
        ensure_output_under_tools(snapshots_dir, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir_arg = str(getattr(args, "output_dir", "") or "").strip() or str(
        to_repo_relative(tools_dir, repo_root)
    )
    try:
        output_dir = resolve_output_dir_under_tools(output_dir_arg, repo_root, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    window = parse_int_arg(getattr(args, "window", ""), default=window_default, minimum=1)
    scan_all = parse_cli_bool(getattr(args, "scan_all", ""), default=scan_all_default)
    limit_md = parse_int_arg(getattr(args, "limit_md", ""), default=limit_md_default, minimum=1)

    ok, code, messages, produced = run_trace_indexer(
        repo_root=repo_root,
        tools_dir=tools_dir,
        trace_history=trace_history,
        deliveries_dir=deliveries_dir,
        snapshots_dir=snapshots_dir,
        output_dir=output_dir,
        window=window,
        scan_all=scan_all,
        limit_md=limit_md,
        policy_cli_args=policy_cli_args,
    )
    for msg in messages:
        print(f"[trace-index] {msg}", file=sys.stderr)
    if produced.get("trace_index_json"):
        print(f"trace_index_json: {produced['trace_index_json']}")
    if produced.get("trace_index_md"):
        print(f"trace_index_md: {produced['trace_index_md']}")

    return 0 if ok else (code if code > 0 else 2)


def cmd_trace_open(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)
    policy, _policy_sources, policy_cli = load_effective_policy(args, repo_root)
    policy_cli_args = policy_subprocess_args(policy_cli)

    trace_id = str(getattr(args, "trace_id", "") or "").strip()
    if not trace_id:
        print("--trace-id is required", file=sys.stderr)
        return 2

    tools_dir_default = str(get_policy_value(policy, "paths.tools_dir", "prompt-dsl-system/tools") or "prompt-dsl-system/tools")
    index_default = str(get_policy_value(policy, "paths.trace_index_json", f"{tools_dir_default}/trace_index.json") or f"{tools_dir_default}/trace_index.json")

    tools_dir_arg = str(getattr(args, "tools_dir", "") or "").strip() or tools_dir_default
    tools_dir = Path(tools_dir_arg)
    if not tools_dir.is_absolute():
        tools_dir = (repo_root / tools_dir).resolve()
    else:
        tools_dir = tools_dir.resolve()
    try:
        ensure_output_under_tools(tools_dir, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    index_arg = str(getattr(args, "index", "") or "").strip() or index_default
    index_path = Path(index_arg)
    if not index_path.is_absolute():
        index_path = (repo_root / index_path).resolve()
    else:
        index_path = index_path.resolve()
    try:
        ensure_output_under_tools(index_path, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_format = str(getattr(args, "output", "text")).strip().lower()
    if output_format not in {"text", "json", "md"}:
        print(f"Invalid --output: {args.output}", file=sys.stderr)
        return 2
    latest = parse_cli_bool(getattr(args, "latest", "true"), default=True)
    emit_restore = parse_cli_bool(getattr(args, "emit_restore", "true"), default=True)
    emit_verify = parse_cli_bool(getattr(args, "emit_verify", "true"), default=True)

    ok, code, messages, _out = run_trace_open(
        repo_root=repo_root,
        tools_dir=tools_dir,
        index_path=index_path,
        trace_id=trace_id,
        output_format=output_format,
        emit_restore=emit_restore,
        emit_verify=emit_verify,
        latest=latest,
        policy_cli_args=policy_cli_args,
    )
    for msg in messages:
        print(f"[trace-open] {msg}", file=sys.stderr)

    return 0 if ok else (code if code > 0 else 2)


def cmd_trace_diff(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)
    policy, _policy_sources, policy_cli = load_effective_policy(args, repo_root)
    policy_cli_args = policy_subprocess_args(policy_cli)

    trace_a = str(getattr(args, "a", "") or "").strip()
    trace_b = str(getattr(args, "b", "") or "").strip()
    if not trace_a:
        print("--a is required", file=sys.stderr)
        return 2
    if not trace_b:
        print("--b is required", file=sys.stderr)
        return 2

    tools_dir_default = str(get_policy_value(policy, "paths.tools_dir", "prompt-dsl-system/tools") or "prompt-dsl-system/tools")
    index_default = str(get_policy_value(policy, "paths.trace_index_json", f"{tools_dir_default}/trace_index.json") or f"{tools_dir_default}/trace_index.json")
    scan_default = parse_cli_bool(get_policy_value(policy, "diff.scan_deliveries_default", False), default=False)
    depth_default = parse_int_arg(get_policy_value(policy, "diff.deliveries_depth", 2), default=2, minimum=0)
    limit_default = parse_int_arg(get_policy_value(policy, "diff.limit_files", 400), default=400, minimum=20)

    tools_dir_arg = str(getattr(args, "tools_dir", "") or "").strip() or tools_dir_default
    tools_dir = Path(tools_dir_arg)
    if not tools_dir.is_absolute():
        tools_dir = (repo_root / tools_dir).resolve()
    else:
        tools_dir = tools_dir.resolve()
    try:
        ensure_output_under_tools(tools_dir, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    index_arg = str(getattr(args, "index", "") or "").strip() or index_default
    index_path = Path(index_arg)
    if not index_path.is_absolute():
        index_path = (repo_root / index_path).resolve()
    else:
        index_path = index_path.resolve()
    try:
        ensure_output_under_tools(index_path, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir_arg = str(getattr(args, "output_dir", "") or "").strip() or str(
        to_repo_relative(tools_dir, repo_root)
    )
    try:
        output_dir = resolve_output_dir_under_tools(output_dir_arg, repo_root, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    latest = parse_cli_bool(getattr(args, "latest", "true"), default=True)
    scan_deliveries = parse_cli_bool(getattr(args, "scan_deliveries", ""), default=scan_default)
    deliveries_depth = parse_int_arg(getattr(args, "deliveries_depth", ""), default=depth_default, minimum=0)
    limit_files = parse_int_arg(getattr(args, "limit_files", ""), default=limit_default, minimum=20)

    output_format = str(getattr(args, "format", "both") or "both").strip().lower()
    if output_format not in {"md", "json", "both"}:
        print(f"Invalid --format: {output_format}", file=sys.stderr)
        return 2

    ok, code, messages, produced = run_trace_diff(
        repo_root=repo_root,
        tools_dir=tools_dir,
        index_path=index_path,
        trace_a=trace_a,
        trace_b=trace_b,
        latest=latest,
        output_dir=output_dir,
        scan_deliveries=scan_deliveries,
        deliveries_depth=deliveries_depth,
        limit_files=limit_files,
        output_format=output_format,
        policy_cli_args=policy_cli_args,
    )
    for msg in messages:
        print(f"[trace-diff] {msg}", file=sys.stderr)
    if produced.get("trace_diff_json"):
        print(f"trace_diff_json: {produced['trace_diff_json']}")
    if produced.get("trace_diff_md"):
        print(f"trace_diff_md: {produced['trace_diff_md']}")

    return 0 if ok else (code if code > 0 else 2)


def cmd_trace_bisect(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)
    policy, _policy_sources, policy_cli = load_effective_policy(args, repo_root)
    policy_cli_args = policy_subprocess_args(policy_cli)

    bad_trace = str(getattr(args, "bad", "") or "").strip()
    if not bad_trace:
        print("--bad is required", file=sys.stderr)
        return 2

    good_trace = str(getattr(args, "good", "") or "").strip()

    tools_dir_default = str(get_policy_value(policy, "paths.tools_dir", "prompt-dsl-system/tools") or "prompt-dsl-system/tools")
    index_default = str(get_policy_value(policy, "paths.trace_index_json", f"{tools_dir_default}/trace_index.json") or f"{tools_dir_default}/trace_index.json")
    auto_find_default = parse_cli_bool(get_policy_value(policy, "bisect.auto_find_good", True), default=True)
    verify_top_default = str(get_policy_value(policy, "bisect.good_verify_top", "PASS") or "PASS").strip().upper()
    max_steps_default = parse_int_arg(get_policy_value(policy, "bisect.max_steps", 12), default=12, minimum=5)

    tools_dir_arg = str(getattr(args, "tools_dir", "") or "").strip() or tools_dir_default
    tools_dir = Path(tools_dir_arg)
    if not tools_dir.is_absolute():
        tools_dir = (repo_root / tools_dir).resolve()
    else:
        tools_dir = tools_dir.resolve()
    try:
        ensure_output_under_tools(tools_dir, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    index_arg = str(getattr(args, "index", "") or "").strip() or index_default
    index_path = Path(index_arg)
    if not index_path.is_absolute():
        index_path = (repo_root / index_path).resolve()
    else:
        index_path = index_path.resolve()
    try:
        ensure_output_under_tools(index_path, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir_arg = str(getattr(args, "output_dir", "") or "").strip() or str(
        to_repo_relative(tools_dir, repo_root)
    )
    try:
        output_dir = resolve_output_dir_under_tools(output_dir_arg, repo_root, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    auto_find_good = parse_cli_bool(getattr(args, "auto_find_good", ""), default=auto_find_default)
    verify_top = str(getattr(args, "verify_top", "") or "").strip().upper() or verify_top_default
    max_steps = parse_int_arg(getattr(args, "max_steps", ""), default=max_steps_default, minimum=5)
    if max_steps > 12:
        max_steps = 12
    emit_sh = parse_cli_bool(getattr(args, "emit_sh", "true"), default=True)
    emit_md = parse_cli_bool(getattr(args, "emit_md", "true"), default=True)

    ok, code, messages, produced = run_trace_bisect_helper(
        repo_root=repo_root,
        tools_dir=tools_dir,
        index_path=index_path,
        bad_trace=bad_trace,
        good_trace=good_trace,
        auto_find_good=auto_find_good,
        verify_top=verify_top,
        output_dir=output_dir,
        max_steps=max_steps,
        emit_sh=emit_sh,
        emit_md=emit_md,
        policy_cli_args=policy_cli_args,
    )
    for msg in messages:
        print(f"[trace-bisect] {msg}", file=sys.stderr)
    if produced.get("bisect_plan_json"):
        print(f"bisect_plan_json: {produced['bisect_plan_json']}")
    if produced.get("bisect_plan_md"):
        print(f"bisect_plan_md: {produced['bisect_plan_md']}")
    if produced.get("bisect_plan_sh"):
        print(f"bisect_plan_sh: {produced['bisect_plan_sh']}")

    return 0 if ok else (code if code > 0 else 2)


def validate_pipeline(
    pipeline_path: Path,
    repo_root: Path,
    registry_by_name: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "pipeline": to_repo_relative(pipeline_path, repo_root),
        "exists": pipeline_path.exists(),
        "yaml_block_count": 0,
        "step_count": 0,
        "errors": [],
        "warnings": [],
        "steps": [],
    }

    if not pipeline_path.exists():
        result["errors"].append(f"Pipeline file not found: {pipeline_path}")
        return result

    text = pipeline_path.read_text(encoding="utf-8")
    blocks = extract_yaml_blocks(text)
    result["yaml_block_count"] = len(blocks)

    step_num = 0
    for block in blocks:
        try:
            parsed = parse_yaml_step_block(block["content"])
        except ParseError as exc:
            result["errors"].append(
                f"YAML block #{block['index']} (line {block['line']}): {exc}"
            )
            continue

        step_num += 1
        step_info = {
            "step": step_num,
            "skill": parsed["skill"],
            "parameters": parsed["parameters"],
            "source_block": block["index"],
            "source_line": block["line"],
        }

        if parsed["skill"] not in registry_by_name:
            result["errors"].append(
                f"Step {step_num}: skill not in registry: {parsed['skill']}"
            )

        for field in REQUIRED_STEP_PARAMS:
            if field not in parsed["parameters"]:
                result["errors"].append(
                    f"Step {step_num}: missing required parameter field: {field}"
                )

        result["steps"].append(sanitize_step_for_report(step_info))

    result["step_count"] = step_num

    if step_num == 0:
        result["errors"].append("No parseable YAML step blocks found in pipeline")

    return result


def write_validate_report(report: Dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_list(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)

    registry, _, errors = load_registry(paths["registry"])
    if errors:
        for err in errors:
            print(f"[ERROR] {err}", file=sys.stderr)
        return 1

    print("name\tdomain\tpath")
    for item in sorted(registry, key=lambda x: (str(x.get("domain", "")), str(x.get("name", "")))):
        print(f"{item.get('name', '')}\t{item.get('domain', '')}\t{item.get('path', '')}")

    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)
    policy, policy_sources, policy_cli = load_effective_policy(args, repo_root)
    policy_cli_args = policy_subprocess_args(policy_cli)
    selected_pipeline: Optional[Path] = None
    health_window_default = parse_int_arg(get_policy_value(policy, "health.window", 20), default=20, minimum=1)
    health_window = parse_int_arg(getattr(args, "health_window", ""), default=health_window_default, minimum=1)
    runbook_mode_default = str(get_policy_value(policy, "health.runbook_mode", "safe") or "safe").strip().lower()
    runbook_mode = str(getattr(args, "runbook_mode", "") or "").strip().lower() or runbook_mode_default
    if runbook_mode not in {"safe", "aggressive"}:
        runbook_mode = "safe"
    trace_history_default = str(get_policy_value(policy, "paths.trace_history", TRACE_HISTORY_REL_PATH) or TRACE_HISTORY_REL_PATH)
    trace_history_path = Path(str(getattr(args, "trace_history", "") or "").strip() or trace_history_default)
    if not trace_history_path.is_absolute():
        trace_history_path = (repo_root / trace_history_path).resolve()
    else:
        trace_history_path = trace_history_path.resolve()

    if args.pipeline:
        selected_pipeline = resolve_pipeline_path(repo_root, args.pipeline)
        if not selected_pipeline.exists():
            rel_hint = "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md"
            abs_hint = str(
                (repo_root / "prompt-dsl-system" / "04_ai_pipeline_orchestration" / "pipeline_sql_oracle_to_dm8.md").resolve()
            )
            print(f"Pipeline file not found: {args.pipeline}", file=sys.stderr)
            print(f"Resolved absolute path: {selected_pipeline}", file=sys.stderr)
            print(f"Suggestion (relative): {rel_hint}", file=sys.stderr)
            print(f"Suggestion (absolute): {abs_hint}", file=sys.stderr)
            return 2

    try:
        effective_module_path, module_path_source = resolve_effective_module_path(
            args.module_path, repo_root, selected_pipeline
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    guard_ok, guard_messages, guard_report = run_path_diff_guard(
        repo_root=repo_root,
        mode="validate",
        module_path=effective_module_path,
        module_path_source=module_path_source,
        advisory=False,
    )
    if not guard_ok:
        for line in guard_messages:
            print(line, file=sys.stderr)
        return 2

    report: Dict[str, Any] = {
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "scope": {
            "effective_module_path": str(effective_module_path) if effective_module_path else None,
            "module_path_source": module_path_source,
            "guard_report_path": GUARD_REPORT_REL_PATH,
            "guard_messages": guard_messages,
            "guard_decision_reason": guard_report.get("decision_reason"),
        },
        "profile": {
            "path": PROFILE_REL_PATH,
            "found": paths["company_profile"].exists(),
            "parsed": False,
            "applied_possible": False,
            "effective_defaults": {},
            "warnings": [],
        },
        "registry": {
            "path": to_repo_relative(paths["registry"], repo_root),
            "exists": paths["registry"].exists(),
            "errors": [],
            "entry_count": 0,
            "missing_skill_files": [],
        },
        "pipelines": [],
        "summary": {
            "pipelines_checked": 0,
            "total_errors": 0,
            "total_warnings": 0,
            "ok": False,
        },
        "policy": {
            "version": str(get_policy_value(policy, "policy_version", "unknown")),
            "sources": policy_sources,
            "effective_path": to_repo_relative((paths["tools_dir"] / "policy_effective.json").resolve(), repo_root),
            "sources_path": to_repo_relative((paths["tools_dir"] / "policy_sources.json").resolve(), repo_root),
            "machine_path": to_repo_relative((paths["tools_dir"] / "policy.json").resolve(), repo_root),
            "errors": [],
        },
    }

    policy_source_files = policy_sources.get("files", []) if isinstance(policy_sources, dict) else []
    for item in policy_source_files:
        if not isinstance(item, dict):
            continue
        loaded = item.get("loaded")
        path_text = str(item.get("path", "")).strip()
        error_text = str(item.get("error", "")).strip()
        if loaded is False and path_text and error_text:
            report["policy"]["errors"].append(
                f"Policy parse check failed ({item.get('kind', 'unknown')}): {path_text} ({error_text})"
            )

    policy_outputs = write_policy_artifacts(
        repo_root=repo_root,
        policy=policy,
        sources=policy_sources,
        tools_dir=paths["tools_dir"],
    )
    report["policy"]["effective_path"] = to_repo_relative(policy_outputs["policy_effective"], repo_root)
    report["policy"]["sources_path"] = to_repo_relative(policy_outputs["policy_sources"], repo_root)
    report["policy"]["machine_path"] = to_repo_relative(policy_outputs["policy_json"], repo_root)

    profile, profile_warnings = load_company_profile(paths["company_profile"])
    report["profile"]["warnings"].extend(profile_warnings)
    report["profile"]["parsed"] = isinstance(profile, dict)
    effective_defaults = profile_effective_defaults(profile)
    report["profile"]["effective_defaults"] = effective_defaults
    report["profile"]["applied_possible"] = bool(effective_defaults)

    registry, registry_by_name, reg_errors = load_registry(paths["registry"])
    report["registry"]["entry_count"] = len(registry)
    report["registry"]["errors"].extend(reg_errors)

    for item in registry:
        p = item.get("path")
        if not isinstance(p, str) or not p.strip():
            report["registry"]["errors"].append(
                f"Invalid registry path for skill: {item.get('name', '<unknown>')}"
            )
            continue
        abs_skill_path = (repo_root / p).resolve()
        if not abs_skill_path.exists():
            report["registry"]["missing_skill_files"].append(
                {
                    "skill": item.get("name"),
                    "path": p,
                }
            )

    pipeline_paths: List[Path] = []
    if args.pipeline:
        if selected_pipeline is not None:
            pipeline_paths.append(selected_pipeline)
    else:
        pipeline_paths = sorted(paths["pipeline_dir"].glob("pipeline_*.md"))
        if not pipeline_paths:
            report["summary"]["total_errors"] += 1
            report["summary"]["ok"] = False
            report["registry"]["errors"].append(
                "No pipeline files found matching prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_*.md"
            )

    for pipeline_path in pipeline_paths:
        pipeline_result = validate_pipeline(pipeline_path, repo_root, registry_by_name)
        report["pipelines"].append(pipeline_result)

    reg_error_count = len(report["registry"]["errors"]) + len(report["registry"]["missing_skill_files"])
    policy_error_count = len(report["policy"].get("errors", []))
    pipe_error_count = sum(len(p.get("errors", [])) for p in report["pipelines"])
    pipe_warn_count = sum(len(p.get("warnings", [])) for p in report["pipelines"])
    profile_warn_count = len(report["profile"].get("warnings", []))

    report["summary"]["pipelines_checked"] = len(report["pipelines"])
    report["summary"]["total_errors"] = reg_error_count + pipe_error_count + policy_error_count
    report["summary"]["total_warnings"] = pipe_warn_count + profile_warn_count
    report["summary"]["ok"] = report["summary"]["total_errors"] == 0

    write_validate_report(report, paths["validate_report"])

    print("Validation Summary")
    print(f"- Registry entries: {report['registry']['entry_count']}")
    print(f"- Pipelines checked: {report['summary']['pipelines_checked']}")
    print(f"- Errors: {report['summary']['total_errors']}")
    print(f"- Warnings: {report['summary']['total_warnings']}")
    print(f"- Report: {to_repo_relative(paths['validate_report'], repo_root)}")
    print(
        "- Policy: loaded (version={version}, sources={count})".format(
            version=report["policy"].get("version", "unknown"),
            count=len(policy_sources.get("files", [])) if isinstance(policy_sources, dict) else 0,
        )
    )
    health_report_ready = False
    if not bool(getattr(args, "no_health_report", False)):
        health_ok, health_messages, health_outputs = run_health_reporter(
            repo_root=repo_root,
            validate_report_path=paths["validate_report"],
            trace_history_path=trace_history_path,
            window=health_window,
            output_dir=paths["tools_dir"],
            include_deliveries=False,
            use_rg=True,
            timezone_mode="local",
            policy_cli_args=policy_cli_args,
        )
        for msg in health_messages:
            print(f"[WARN] {msg}", file=sys.stderr)
        health_md = health_outputs.get("health_report_md")
        if health_md:
            print(f"Health report generated: {health_md}")
            health_report_ready = True
        elif health_ok:
            print(
                f"Health report generated: {to_repo_relative(paths['health_report_md'], repo_root)}"
            )
            health_report_ready = True
    else:
        health_report_ready = paths["health_report_json"].exists()

    if not bool(getattr(args, "no_health_runbook", False)):
        if health_report_ready and paths["health_report_json"].exists():
            runbook_ok, runbook_messages, runbook_outputs = run_health_runbook_generator(
                repo_root=repo_root,
                health_report_path=paths["health_report_json"],
                output_dir=paths["tools_dir"],
                mode=runbook_mode,
                include_ack_flows=True,
                shell="bash",
                emit_sh=True,
                emit_md=True,
                policy_cli_args=policy_cli_args,
            )
            for msg in runbook_messages:
                print(f"[WARN] {msg}", file=sys.stderr)
            runbook_md = runbook_outputs.get("health_runbook_md")
            if runbook_md:
                print(f"Health runbook generated: {runbook_md}")
            elif runbook_ok:
                print(
                    f"Health runbook generated: {to_repo_relative(paths['tools_dir'] / 'health_runbook.md', repo_root)}"
                )
        else:
            print(
                "[WARN] skip health runbook generation: health_report.json not ready",
                file=sys.stderr,
            )

    return 0 if report["summary"]["ok"] else 1


def to_yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{s}"'


def normalize_step_parameters(params: Dict[str, Any], context_id: str, trace_id: str) -> Dict[str, Any]:
    normalized = dict(params)
    normalized["context_id"] = context_id
    normalized["trace_id"] = trace_id

    refs = normalized.get("input_artifact_refs")
    if isinstance(refs, list):
        normalized["input_artifact_refs"] = refs
    elif refs is None or refs == "":
        normalized["input_artifact_refs"] = []
    else:
        normalized["input_artifact_refs"] = [refs]

    return normalized


def ordered_parameter_items(params: Dict[str, Any]) -> List[Tuple[str, Any]]:
    first = ["context_id", "trace_id", "input_artifact_refs"]
    seen = set(first)
    tail = sorted([k for k in params.keys() if k not in seen])
    ordered_keys = [k for k in first if k in params] + tail
    return [(k, params[k]) for k in ordered_keys]


def build_handoff_hint(current_idx: int, steps: List[Dict[str, Any]]) -> str:
    if current_idx >= len(steps) - 1:
        return "Final step."

    next_refs = steps[current_idx + 1]["parameters"].get("input_artifact_refs")
    if isinstance(next_refs, list) and next_refs:
        joined = ", ".join(str(x) for x in next_refs)
        return f"来自下一步引用：{joined}（来自上一步 artifacts）"

    return "可选：在下一步 input_artifact_refs 中填入上一步 artifacts 编号。"


def write_run_plan(run_plan: Dict[str, Any], output_path: Path) -> None:
    lines: List[str] = []

    run_meta = run_plan["run"]
    lines.append("run:")
    lines.append(f"  pipeline: {to_yaml_scalar(run_meta['pipeline'])}")
    lines.append(f"  context_id: {to_yaml_scalar(run_meta['context_id'])}")
    lines.append(f"  trace_id: {to_yaml_scalar(run_meta['trace_id'])}")
    lines.append(f"  generated_at: {to_yaml_scalar(run_meta['generated_at'])}")
    lines.append(f"  effective_module_path: {to_yaml_scalar(run_meta.get('effective_module_path'))}")
    lines.append(f"  module_path_source: {to_yaml_scalar(run_meta.get('module_path_source', 'none'))}")
    profile_meta = run_meta.get("profile", {})
    lines.append("  profile:")
    lines.append(f"    path: {to_yaml_scalar(profile_meta.get('path', PROFILE_REL_PATH))}")
    lines.append(f"    applied: {to_yaml_scalar(bool(profile_meta.get('applied', False)))}")
    injected_defaults = profile_meta.get("injected_defaults")
    if isinstance(injected_defaults, dict) and injected_defaults:
        lines.append("    injected_defaults:")
        for key in sorted(injected_defaults.keys()):
            value = injected_defaults[key]
            if isinstance(value, dict):
                lines.append(f"      {key}:")
                for sub_key in sorted(value.keys()):
                    lines.append(f"        {sub_key}: {to_yaml_scalar(value[sub_key])}")
            elif isinstance(value, list):
                if not value:
                    lines.append(f"      {key}: []")
                else:
                    lines.append(f"      {key}:")
                    for item in value:
                        lines.append(f"        - {to_yaml_scalar(item)}")
            else:
                lines.append(f"      {key}: {to_yaml_scalar(value)}")
    else:
        lines.append("    injected_defaults: {}")

    lines.append("steps:")
    for step in run_plan["steps"]:
        lines.append(f"  - step: {step['step']}")
        lines.append(f"    skill: {to_yaml_scalar(step['skill'])}")
        lines.append(f"    skill_path: {to_yaml_scalar(step['skill_path'])}")
        lines.append("    parameters:")

        for key, value in ordered_parameter_items(step["parameters"]):
            if isinstance(value, list):
                if not value:
                    lines.append(f"      {key}: []")
                else:
                    lines.append(f"      {key}:")
                    for item in value:
                        lines.append(f"        - {to_yaml_scalar(item)}")
            else:
                lines.append(f"      {key}: {to_yaml_scalar(value)}")

        lines.append("    expects:")
        lines.append("      artifacts:")
        for artifact in step["expects"]["artifacts"]:
            lines.append(f"        - {to_yaml_scalar(artifact)}")
        lines.append(f"      notes: {to_yaml_scalar(step['expects']['notes'])}")
        lines.append(f"    handoff: {to_yaml_scalar(step['handoff'])}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_run(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not assert_repo_root(repo_root):
        return 2
    paths = resolve_repo_paths(repo_root)
    policy, _policy_sources, policy_cli = load_effective_policy(args, repo_root)
    policy_cli_args = policy_subprocess_args(policy_cli)

    pipeline_path = resolve_pipeline_path(repo_root, args.pipeline)
    if not pipeline_path.exists():
        print(f"[ERROR] Pipeline file not found: {pipeline_path}", file=sys.stderr)
        return 1

    context_id = args.context_id or f"ctx-{uuid4().hex[:12]}"
    trace_id = args.trace_id or f"trace-{uuid4().hex}"
    loop_window_default = parse_int_arg(
        get_policy_value(policy, "gates.loop_gate.window", 6), default=6, minimum=2
    )
    loop_window = parse_int_arg(args.loop_window, default=loop_window_default, minimum=2)
    loop_exit_code = parse_int_arg(args.loop_exit_code, default=3, minimum=1)
    loop_same_trace_only = parse_cli_bool(args.loop_same_trace_only, default=True)
    fail_on_loop_default = parse_cli_bool(
        get_policy_value(policy, "gates.loop_gate.fail_on_loop_high", False), default=False
    )
    fail_on_loop = bool(args.fail_on_loop) or fail_on_loop_default
    risk_gate_default = parse_cli_bool(
        get_policy_value(policy, "gates.guard_gate.enabled", True), default=True
    )
    risk_gate_enabled = parse_cli_bool(args.risk_gate, default=risk_gate_default)
    if bool(getattr(args, "no_risk_gate", False)):
        risk_gate_enabled = False
    risk_threshold = str(args.risk_threshold).strip().upper()
    verify_gate_default = parse_cli_bool(
        get_policy_value(policy, "gates.verify_gate.enabled", True), default=True
    )
    verify_gate_enabled = parse_cli_bool(args.verify_gate, default=verify_gate_default)
    verify_threshold = str(args.verify_threshold).strip().upper()
    verify_refresh = parse_cli_bool(args.verify_refresh, default=False)
    if verify_threshold not in {"PASS", "WARN", "FAIL"}:
        print(f"Invalid --verify-threshold: {args.verify_threshold}", file=sys.stderr)
        return 2
    risk_ttl_minutes = parse_int_arg(args.risk_ttl_minutes, default=30, minimum=0)
    risk_exit_code = parse_int_arg(args.risk_exit_code, default=4, minimum=1)

    try:
        loop_output_dir = resolve_output_dir_under_tools(
            str(args.loop_output_dir).strip()
            or str(get_policy_value(policy, "paths.tools_dir", "prompt-dsl-system/tools")),
            repo_root,
            paths["tools_dir"],
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    risk_token_out = Path(args.risk_token_out)
    if not risk_token_out.is_absolute():
        risk_token_out = (repo_root / risk_token_out).resolve()
    else:
        risk_token_out = risk_token_out.resolve()
    try:
        ensure_output_under_tools(risk_token_out, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    risk_token_json_out = Path(args.risk_token_json_out)
    if not risk_token_json_out.is_absolute():
        risk_token_json_out = (repo_root / risk_token_json_out).resolve()
    else:
        risk_token_json_out = risk_token_json_out.resolve()
    try:
        ensure_output_under_tools(risk_token_json_out, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    risk_json_out = (loop_output_dir / "risk_gate_report.json").resolve()
    risk_guard_report = (loop_output_dir / "guard_report.json").resolve()
    risk_loop_report = (loop_output_dir / "loop_diagnostics.json").resolve()
    risk_move_report = (loop_output_dir / "move_report.json").resolve()
    verify_report_path = Path(args.verify_report)
    if not verify_report_path.is_absolute():
        verify_report_path = (repo_root / verify_report_path).resolve()
    else:
        verify_report_path = verify_report_path.resolve()
    try:
        ensure_output_under_tools(verify_report_path, paths["tools_dir"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    ack_used = normalize_ack_used(
        ack_source=getattr(args, "ack_source", None),
        ack=args.ack,
        ack_file=getattr(args, "ack_file", None),
        ack_latest=bool(getattr(args, "ack_latest", False)),
    )
    ack_token, ack_err = resolve_ack_token(
        repo_root=repo_root,
        output_dir=loop_output_dir,
        ack=args.ack,
        ack_file=getattr(args, "ack_file", None),
        ack_latest=bool(getattr(args, "ack_latest", False)),
    )
    if ack_err:
        print(f"[run][error] {ack_err}", file=sys.stderr)
        return 2
    if ack_token is None:
        ack_used = "none"
    elif ack_used == "none":
        ack_used = "ack"

    verify_trace_state = parse_verify_from_gate_report(
        gate_report={},
        verify_report_path=verify_report_path,
        verify_gate_enabled=verify_gate_enabled,
        verify_threshold=verify_threshold,
    )

    try:
        effective_module_path, module_path_source = resolve_effective_module_path(
            args.module_path, repo_root, pipeline_path
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    guard_ok, guard_messages, guard_report = run_path_diff_guard(
        repo_root=repo_root,
        mode="run",
        module_path=effective_module_path,
        module_path_source=module_path_source,
        advisory=False,
    )
    if not guard_ok:
        for line in guard_messages:
            print(line, file=sys.stderr)
        guard_blocked_record = build_trace_record(
            repo_root=repo_root,
            context_id=context_id,
            trace_id=trace_id,
            command="run",
            pipeline_path=pipeline_path,
            effective_module_path=effective_module_path,
            module_path_source=module_path_source,
            guard_report=guard_report,
            action="blocked",
            verify_status=verify_trace_state["verify_status"],
            verify_hits_total=verify_trace_state["verify_hits_total"],
            verify_gate_required=verify_trace_state["verify_gate_required"],
            verify_gate_triggered=False,
            ack_used=ack_used,
            blocked_by="guard_gate",
            exit_code=2,
        )
        try:
            append_trace_history(repo_root, guard_blocked_record)
        except OSError as exc:
            print(f"[WARN] failed to append trace history: {exc}", file=sys.stderr)
        return 2

    if risk_gate_enabled or verify_gate_enabled:
        pre_guard_ok, pre_guard_msgs, _pre_guard_report = run_path_diff_guard(
            repo_root=repo_root,
            mode="debug-guard",
            module_path=effective_module_path,
            module_path_source=module_path_source,
            advisory=True,
        )
        if not pre_guard_ok:
            for msg in pre_guard_msgs:
                print(f"[risk-gate][warn] {msg}", file=sys.stderr)

        default_guard_report = (repo_root / GUARD_REPORT_REL_PATH).resolve()
        copy_guard_report(default_guard_report, risk_guard_report)

        pre_plan_ok, pre_plan_msgs, _pre_paths = run_rollback_helper_for_debug_guard(
            repo_root=repo_root,
            output_dir=loop_output_dir,
            report_rel_path=to_repo_relative(risk_guard_report, repo_root),
            module_path=effective_module_path,
            only_violations=True,
            plans="both",
        )
        if not pre_plan_ok:
            for msg in pre_plan_msgs:
                print(f"[risk-gate][warn] {msg}", file=sys.stderr)

        pre_loop_ok, _pre_loop_diag, pre_loop_msgs = run_loop_detector(
            repo_root=repo_root,
            output_dir=loop_output_dir,
            context_id=context_id,
            trace_id=trace_id,
            pipeline_path=pipeline_path,
            effective_module_path=effective_module_path,
            window=loop_window,
            same_trace_only=loop_same_trace_only,
            policy_cli_args=policy_cli_args,
        )
        if not pre_loop_ok:
            for msg in pre_loop_msgs:
                print(f"[risk-gate][warn] {msg}", file=sys.stderr)

        if not risk_loop_report.exists():
            risk_loop_report.write_text(
                json.dumps(
                    {
                        "generated_at": now_iso(),
                        "level": "NONE",
                        "triggers": [],
                        "recommendation": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        gate1_ok, gate1_code, gate1_report, gate1_messages = ensure_release_gate(
            repo_root=repo_root,
            command_name="run",
            module_path=effective_module_path,
            module_path_source=module_path_source,
            output_dir=loop_output_dir,
            guard_report_path=risk_guard_report,
            loop_report_path=risk_loop_report,
            move_report_path=risk_move_report,
            ack=ack_token,
            verify_gate_enabled=verify_gate_enabled,
            verify_threshold=verify_threshold,
            verify_report_path=verify_report_path,
            verify_refresh=verify_refresh,
            risk_gate_enabled=risk_gate_enabled,
            risk_threshold=risk_threshold,
            risk_ttl_minutes=risk_ttl_minutes,
            risk_exit_code=risk_exit_code,
            token_out=risk_token_out,
            token_json_out=risk_token_json_out,
            json_out=risk_json_out,
            consume_on_pass=False,
            policy_cli_args=policy_cli_args,
        )
        for msg in gate1_messages:
            print(f"[risk-gate][warn] {msg}", file=sys.stderr)
        if not gate1_ok:
            verify_trace_state = parse_verify_from_gate_report(
                gate1_report,
                verify_report_path=verify_report_path,
                verify_gate_enabled=verify_gate_enabled,
                verify_threshold=verify_threshold,
            )
            overall_risk = str(gate1_report.get("overall_risk", "unknown"))
            token_rel = to_repo_relative(risk_token_out, repo_root)
            next_cmd = gate1_report.get("next_cmd")
            if not isinstance(next_cmd, str) or not next_cmd.strip():
                next_cmd = (
                    "./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> "
                    f"--pipeline {to_repo_relative(pipeline_path, repo_root)} --ack-latest"
                )
            print(
                f"[risk-gate] blocked before run plan: overall_risk={overall_risk}",
                file=sys.stderr,
            )
            print(f"[risk-gate] token file: {token_rel}", file=sys.stderr)
            print(f"NEXT_CMD: {next_cmd}", file=sys.stderr)
            gate1_record = build_trace_record(
                repo_root=repo_root,
                context_id=context_id,
                trace_id=trace_id,
                command="run",
                pipeline_path=pipeline_path,
                effective_module_path=effective_module_path,
                module_path_source=module_path_source,
                guard_report=guard_report,
                action="blocked",
                verify_status=verify_trace_state["verify_status"],
                verify_hits_total=verify_trace_state["verify_hits_total"],
                verify_gate_required=verify_trace_state["verify_gate_required"],
                verify_gate_triggered=verify_trace_state["verify_gate_triggered"],
                ack_used=ack_used,
                blocked_by=detect_blocked_by_from_gate_report(gate1_report),
                exit_code=gate1_code if gate1_code > 0 else risk_exit_code,
            )
            try:
                append_trace_history(repo_root, gate1_record)
            except OSError as exc:
                print(f"[WARN] failed to append trace history: {exc}", file=sys.stderr)
            append_ack_note(
                repo_root=repo_root,
                command="run",
                context_id=context_id,
                trace_id=trace_id,
                note=getattr(args, "ack_note", None),
                verify_status=verify_trace_state["verify_status"],
                verify_hits_total=verify_trace_state["verify_hits_total"],
                ack_used=ack_used,
            )
            return gate1_code if gate1_code > 0 else risk_exit_code

    _, registry_by_name, reg_errors = load_registry(paths["registry"])
    if reg_errors:
        for err in reg_errors:
            print(f"[ERROR] {err}", file=sys.stderr)
        return 1

    text = pipeline_path.read_text(encoding="utf-8")
    blocks = extract_yaml_blocks(text)
    if not blocks:
        print("[ERROR] No YAML blocks found in pipeline", file=sys.stderr)
        return 1

    profile, _profile_warnings = load_company_profile(paths["company_profile"])
    profile_applied = False
    injected_defaults_agg: Dict[str, List[Any]] = {}

    parsed_steps: List[Dict[str, Any]] = []
    for block in blocks:
        try:
            parsed = parse_yaml_step_block(block["content"])
        except ParseError as exc:
            print(
                f"[ERROR] YAML block #{block['index']} (line {block['line']}) parse failed: {exc}",
                file=sys.stderr,
            )
            return 1

        skill_name = parsed["skill"]
        if skill_name not in registry_by_name:
            print(f"[ERROR] Skill not found in registry: {skill_name}", file=sys.stderr)
            return 1

        step_params = normalize_step_parameters(parsed["parameters"], context_id=context_id, trace_id=trace_id)
        step_params, injected_defaults = inject_profile_defaults(step_params, profile)
        if injected_defaults:
            profile_applied = True
            for key, value in injected_defaults.items():
                values = injected_defaults_agg.setdefault(key, [])
                if value not in values:
                    values.append(value)
        parsed_steps.append(
            {
                "skill": skill_name,
                "skill_path": registry_by_name[skill_name]["path"],
                "parameters": step_params,
            }
        )

    run_plan_steps: List[Dict[str, Any]] = []
    for idx, step in enumerate(parsed_steps, start=1):
        run_plan_steps.append(
            {
                "step": idx,
                "skill": step["skill"],
                "skill_path": step["skill_path"],
                "parameters": step["parameters"],
                "expects": {
                    "artifacts": ["A1", "A2"],
                    "notes": "Artifacts must be numbered A1/A2/... per SKILL_SPEC.",
                },
                "handoff": "",  # fill below
            }
        )

    for idx in range(len(run_plan_steps)):
        run_plan_steps[idx]["handoff"] = build_handoff_hint(idx, run_plan_steps)

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = (repo_root / out_path).resolve()
    ensure_output_under_tools(out_path, paths["tools_dir"])

    injected_defaults_compact: Dict[str, Any] = {}
    for key, values in injected_defaults_agg.items():
        if len(values) == 1:
            injected_defaults_compact[key] = values[0]
        else:
            injected_defaults_compact[key] = values

    run_plan = {
        "run": {
            "pipeline": to_repo_relative(pipeline_path, repo_root),
            "context_id": context_id,
            "trace_id": trace_id,
            "generated_at": now_iso(),
            "effective_module_path": str(effective_module_path) if effective_module_path else None,
            "module_path_source": module_path_source,
            "profile": {
                "path": PROFILE_REL_PATH,
                "applied": profile_applied,
                "injected_defaults": injected_defaults_compact,
            },
        },
        "steps": run_plan_steps,
    }

    write_run_plan(run_plan, out_path)

    print("Run plan generated")
    print(f"- Pipeline: {to_repo_relative(pipeline_path, repo_root)}")
    print(f"- Steps: {len(run_plan_steps)}")
    print(f"- Context ID: {context_id}")
    print(f"- Trace ID: {trace_id}")
    print(f"- Output: {to_repo_relative(out_path, repo_root)}")
    loop_action = "run_plan_generated"
    loop_level = "NONE"

    loop_ok, loop_diag, loop_messages = run_loop_detector(
        repo_root=repo_root,
        output_dir=loop_output_dir,
        context_id=context_id,
        trace_id=trace_id,
        pipeline_path=pipeline_path,
        effective_module_path=effective_module_path,
        window=loop_window,
        same_trace_only=loop_same_trace_only,
        policy_cli_args=policy_cli_args,
    )
    if not loop_ok:
        for msg in loop_messages:
            print(f"[WARN] {msg}", file=sys.stderr)
    else:
        loop_level = str(loop_diag.get("level", "NONE")).upper()
        if loop_level in {"MEDIUM", "HIGH"}:
            triggers = loop_diag.get("triggers", [])
            trigger_names: List[str] = []
            if isinstance(triggers, list):
                for item in triggers:
                    if isinstance(item, dict):
                        trigger_names.append(str(item.get("id", "unknown")))
                    else:
                        trigger_names.append(str(item))
            trigger_text = ", ".join(trigger_names) if trigger_names else "unknown"
            print(
                f"[LOOP][{loop_level}] potential anti-loop trigger(s): {trigger_text}",
                file=sys.stderr,
            )

            loop_guard_ok, loop_guard_msgs, _loop_guard_report = run_path_diff_guard(
                repo_root=repo_root,
                mode="debug-guard",
                module_path=effective_module_path,
                module_path_source=module_path_source,
                advisory=True,
            )
            if not loop_guard_ok:
                for msg in loop_guard_msgs:
                    print(f"[LOOP][warn] {msg}", file=sys.stderr)

            default_guard_report = (repo_root / GUARD_REPORT_REL_PATH).resolve()
            loop_guard_report = (loop_output_dir / "guard_report.json").resolve()
            copy_guard_report(default_guard_report, loop_guard_report)

            loop_plan_ok, loop_plan_msgs, _loop_paths = run_rollback_helper_for_debug_guard(
                repo_root=repo_root,
                output_dir=loop_output_dir,
                report_rel_path=to_repo_relative(loop_guard_report, repo_root),
                module_path=effective_module_path,
                only_violations=True,
                plans="both",
            )
            if not loop_plan_ok:
                for msg in loop_plan_msgs:
                    print(f"[LOOP][warn] {msg}", file=sys.stderr)

            diag_rel = to_repo_relative(loop_output_dir / "loop_diagnostics.md", repo_root)
            guard_rel = to_repo_relative(loop_guard_report, repo_root)
            print("[LOOP] intervention checklist:", file=sys.stderr)
            print(f"1) Review {diag_rel}", file=sys.stderr)
            print(f"2) Review {guard_rel}", file=sys.stderr)
            print(
                "3) Fix scope violations via apply-move: ./prompt-dsl-system/tools/run.sh apply-move -r . -m <MODULE_PATH> --yes --move-dry-run false",
                file=sys.stderr,
            )
            print(
                "4) If still failing, execute rollback plan: ./prompt-dsl-system/tools/run.sh rollback -r . -m <MODULE_PATH> --report "
                + to_repo_relative(loop_guard_report, repo_root),
                file=sys.stderr,
            )

            if fail_on_loop and loop_level == "HIGH":
                loop_action = "loop_blocked"
                loop_block_record = build_trace_record(
                    repo_root=repo_root,
                    context_id=context_id,
                    trace_id=trace_id,
                    command="run",
                    pipeline_path=pipeline_path,
                    effective_module_path=effective_module_path,
                    module_path_source=module_path_source,
                    guard_report=guard_report,
                    action="blocked",
                    verify_status=verify_trace_state["verify_status"],
                    verify_hits_total=verify_trace_state["verify_hits_total"],
                    verify_gate_required=verify_trace_state["verify_gate_required"],
                    verify_gate_triggered=verify_trace_state["verify_gate_triggered"],
                    ack_used=ack_used,
                    blocked_by="loop_gate",
                    exit_code=loop_exit_code,
                )
                try:
                    append_trace_history(repo_root, loop_block_record)
                except OSError as exc:
                    print(f"[WARN] failed to append trace history: {exc}", file=sys.stderr)
                print(
                    f"[LOOP][HIGH] fail-on-loop enabled; blocked with exit code {loop_exit_code}",
                    file=sys.stderr,
                )
                return loop_exit_code

            loop_action = "loop_warned"

    if risk_gate_enabled or verify_gate_enabled:
        default_guard_report = (repo_root / GUARD_REPORT_REL_PATH).resolve()
        copy_guard_report(default_guard_report, risk_guard_report)
        if not risk_loop_report.exists():
            risk_loop_report.write_text(
                json.dumps(
                    {
                        "generated_at": now_iso(),
                        "level": loop_level,
                        "triggers": [],
                        "recommendation": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        gate2_ok, gate2_code, gate2_report, gate2_messages = ensure_release_gate(
            repo_root=repo_root,
            command_name="run",
            module_path=effective_module_path,
            module_path_source=module_path_source,
            output_dir=loop_output_dir,
            guard_report_path=risk_guard_report,
            loop_report_path=risk_loop_report,
            move_report_path=risk_move_report,
            ack=ack_token,
            verify_gate_enabled=verify_gate_enabled,
            verify_threshold=verify_threshold,
            verify_report_path=verify_report_path,
            verify_refresh=verify_refresh,
            risk_gate_enabled=risk_gate_enabled,
            risk_threshold=risk_threshold,
            risk_ttl_minutes=risk_ttl_minutes,
            risk_exit_code=risk_exit_code,
            token_out=risk_token_out,
            token_json_out=risk_token_json_out,
            json_out=risk_json_out,
            consume_on_pass=True,
            policy_cli_args=policy_cli_args,
        )
        for msg in gate2_messages:
            print(f"[risk-gate][warn] {msg}", file=sys.stderr)
        if not gate2_ok:
            verify_trace_state = parse_verify_from_gate_report(
                gate2_report,
                verify_report_path=verify_report_path,
                verify_gate_enabled=verify_gate_enabled,
                verify_threshold=verify_threshold,
            )
            overall_risk = str(gate2_report.get("overall_risk", "unknown"))
            token_rel = to_repo_relative(risk_token_out, repo_root)
            next_cmd = gate2_report.get("next_cmd")
            if not isinstance(next_cmd, str) or not next_cmd.strip():
                next_cmd = (
                    "./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> "
                    f"--pipeline {to_repo_relative(pipeline_path, repo_root)} --ack-latest"
                )
            print(
                f"[risk-gate] blocked after run plan: overall_risk={overall_risk}",
                file=sys.stderr,
            )
            print(f"[risk-gate] token file: {token_rel}", file=sys.stderr)
            print(f"NEXT_CMD: {next_cmd}", file=sys.stderr)
            gate2_record = build_trace_record(
                repo_root=repo_root,
                context_id=context_id,
                trace_id=trace_id,
                command="run",
                pipeline_path=pipeline_path,
                effective_module_path=effective_module_path,
                module_path_source=module_path_source,
                guard_report=guard_report,
                action="blocked",
                verify_status=verify_trace_state["verify_status"],
                verify_hits_total=verify_trace_state["verify_hits_total"],
                verify_gate_required=verify_trace_state["verify_gate_required"],
                verify_gate_triggered=verify_trace_state["verify_gate_triggered"],
                ack_used=ack_used,
                blocked_by=detect_blocked_by_from_gate_report(gate2_report),
                exit_code=gate2_code if gate2_code > 0 else risk_exit_code,
            )
            try:
                append_trace_history(repo_root, gate2_record)
            except OSError as exc:
                print(f"[WARN] failed to append trace history: {exc}", file=sys.stderr)
            append_ack_note(
                repo_root=repo_root,
                command="run",
                context_id=context_id,
                trace_id=trace_id,
                note=getattr(args, "ack_note", None),
                verify_status=verify_trace_state["verify_status"],
                verify_hits_total=verify_trace_state["verify_hits_total"],
                ack_used=ack_used,
            )
            return gate2_code if gate2_code > 0 else risk_exit_code
        verify_trace_state = parse_verify_from_gate_report(
            gate2_report,
            verify_report_path=verify_report_path,
            verify_gate_enabled=verify_gate_enabled,
            verify_threshold=verify_threshold,
        )

    final_record = build_trace_record(
        repo_root=repo_root,
        context_id=context_id,
        trace_id=trace_id,
        command="run",
        pipeline_path=pipeline_path,
        effective_module_path=effective_module_path,
        module_path_source=module_path_source,
        guard_report=guard_report,
        action=loop_action,
        verify_status=verify_trace_state["verify_status"],
        verify_hits_total=verify_trace_state["verify_hits_total"],
        verify_gate_required=verify_trace_state["verify_gate_required"],
        verify_gate_triggered=verify_trace_state["verify_gate_triggered"],
        ack_used=ack_used,
        blocked_by="none",
        exit_code=0,
    )
    try:
        append_trace_history(repo_root, final_record)
    except OSError as exc:
        print(f"[WARN] failed to append trace history: {exc}", file=sys.stderr)

    append_ack_note(
        repo_root=repo_root,
        command="run",
        context_id=context_id,
        trace_id=trace_id,
        note=getattr(args, "ack_note", None),
        verify_status=verify_trace_state["verify_status"],
        verify_hits_total=verify_trace_state["verify_hits_total"],
        ack_used=ack_used,
    )

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pipeline runner for prompt-dsl-system")
    parser.add_argument(
        "--policy",
        default="",
        help="Optional policy YAML path (global, applies to all subcommands)",
    )
    parser.add_argument(
        "--policy-override",
        action="append",
        default=[],
        help="Policy override key=value (repeatable, global)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list", help="List skills from registry")
    list_p.add_argument("--repo-root", default=".", help="Repository root path")
    list_p.add_argument("--module-path", help="Optional module boundary path")
    list_p.set_defaults(func=cmd_list)

    validate_p = sub.add_parser("validate", help="Validate registry and pipelines")
    validate_p.add_argument("--repo-root", default=".", help="Repository root path")
    validate_p.add_argument("--module-path", help="Optional module boundary path")
    validate_p.add_argument(
        "--pipeline",
        help="Optional specific pipeline markdown path; if omitted validates all pipeline_*.md",
    )
    validate_p.add_argument("--health-window", default="", help="Health report trace window size")
    validate_p.add_argument(
        "--trace-history",
        default="",
        help="Trace history jsonl path for health report",
    )
    validate_p.add_argument(
        "--no-health-report",
        action="store_true",
        help="Skip automatic health_report generation after validate",
    )
    validate_p.add_argument(
        "--no-health-runbook",
        action="store_true",
        help="Skip automatic health_runbook generation after validate",
    )
    validate_p.add_argument(
        "--runbook-mode",
        default="",
        choices=["safe", "aggressive", ""],
        help="Health runbook mode",
    )
    validate_p.set_defaults(func=cmd_validate)

    run_p = sub.add_parser("run", help="Generate run plan from one pipeline")
    run_p.add_argument("--repo-root", default=".", help="Repository root path")
    run_p.add_argument("--module-path", help="Optional module boundary path")
    run_p.add_argument("--pipeline", required=True, help="Pipeline markdown path")
    run_p.add_argument("--context-id", help="Optional context id")
    run_p.add_argument("--trace-id", help="Optional trace id")
    run_p.add_argument(
        "--out",
        default="prompt-dsl-system/tools/run_plan.yaml",
        help="Output path for run plan (must be under prompt-dsl-system/tools)",
    )
    run_p.add_argument("--loop-window", default="", help="Loop detection window size (policy default if omitted)")
    run_p.add_argument(
        "--fail-on-loop",
        action="store_true",
        help="Fail fast when loop level is HIGH (exit code from --loop-exit-code)",
    )
    run_p.add_argument("--loop-exit-code", default="3", help="Exit code when loop blocking is enabled")
    run_p.add_argument(
        "--loop-output-dir",
        default="",
        help="Output directory for loop diagnostics and loop-triggered plans (must be under prompt-dsl-system/tools)",
    )
    run_p.add_argument(
        "--loop-same-trace-only",
        default="true",
        help="true/false, default true; true=analyze same trace_id only",
    )
    run_p.add_argument("--risk-gate", default="", help="true/false, policy default if omitted")
    run_p.add_argument("--no-risk-gate", action="store_true", help="Disable risk gate")
    run_p.add_argument("--risk-threshold", default="HIGH", help="LOW|MEDIUM|HIGH, default HIGH")
    run_p.add_argument("--ack", help="One-time risk gate ACK token")
    run_p.add_argument("--ack-file", help="Risk gate token json file")
    run_p.add_argument("--ack-latest", action="store_true", help="Use latest token from output-dir")
    run_p.add_argument("--ack-source", help=argparse.SUPPRESS)
    run_p.add_argument("--ack-note", help="Optional rationale note when ACK is used under verify FAIL")
    run_p.add_argument("--verify-gate", default="", help="true/false, policy default if omitted")
    run_p.add_argument("--verify-threshold", default="FAIL", help="PASS|WARN|FAIL, default FAIL")
    run_p.add_argument(
        "--verify-report",
        default="prompt-dsl-system/tools/followup_verify_report.json",
        help="Follow-up verify report path (must be under prompt-dsl-system/tools)",
    )
    run_p.add_argument("--verify-refresh", default="false", help="true/false, default false")
    run_p.add_argument("--risk-ttl-minutes", default="30", help="ACK token TTL minutes, default 30")
    run_p.add_argument("--risk-exit-code", default="4", help="Risk gate block exit code, default 4")
    run_p.add_argument(
        "--risk-token-out",
        default="prompt-dsl-system/tools/RISK_GATE_TOKEN.txt",
        help="Risk gate token output path (must be under prompt-dsl-system/tools)",
    )
    run_p.add_argument(
        "--risk-token-json-out",
        default=RISK_TOKEN_JSON_REL_PATH,
        help="Risk gate token JSON output path (must be under prompt-dsl-system/tools)",
    )
    run_p.set_defaults(func=cmd_run)

    dbg_p = sub.add_parser("debug-guard", help="Inspect guardrails and run advisory guard check")
    dbg_p.add_argument("--repo-root", default=".", help="Repository root path")
    dbg_p.add_argument("--module-path", help="Optional module boundary path")
    dbg_p.add_argument("--pipeline", help="Optional pipeline path for module_path derivation")
    dbg_p.add_argument("--generate-plans", default="true", help="true/false, default true")
    dbg_p.add_argument("--plans", choices=["move", "rollback", "both"], default="both")
    dbg_p.add_argument(
        "--output-dir",
        default="prompt-dsl-system/tools",
        help="Output directory for generated plans (must be under prompt-dsl-system/tools)",
    )
    dbg_p.add_argument("--only-violations", default="true", help="true/false, default true")
    dbg_p.set_defaults(func=cmd_debug_guard)

    apply_move_p = sub.add_parser(
        "apply-move",
        help="Apply move plan with explicit confirmation, then advisory recheck",
    )
    apply_move_p.add_argument("--repo-root", default=".", help="Repository root path")
    apply_move_p.add_argument("--module-path", help="Module boundary path (recommended)")
    apply_move_p.add_argument(
        "--report",
        default=GUARD_REPORT_REL_PATH,
        help="Guard report path (must be under --output-dir)",
    )
    apply_move_p.add_argument("--only-violations", default="true", help="true/false, default true")
    apply_move_p.add_argument("--yes", action="store_true", help="Required to execute real file moves")
    apply_move_p.add_argument("--move-dry-run", default="true", help="true/false, default true")
    apply_move_p.add_argument("--ack", help="Risk gate ACK token for release gate")
    apply_move_p.add_argument("--ack-file", help="Risk gate token json file")
    apply_move_p.add_argument("--ack-latest", action="store_true", help="Use latest token from output-dir")
    apply_move_p.add_argument("--ack-source", help=argparse.SUPPRESS)
    apply_move_p.add_argument("--ack-note", help="Optional rationale note when ACK is used under verify FAIL")
    apply_move_p.add_argument("--context-id", help="Optional context id for trace history")
    apply_move_p.add_argument("--trace-id", help="Optional trace id for trace history")
    apply_move_p.add_argument("--snapshot", default="", help="true/false, policy default if omitted")
    apply_move_p.add_argument("--no-snapshot", action="store_true", help="Disable pre-apply snapshot")
    apply_move_p.add_argument(
        "--snapshot-dir",
        default="",
        help="Snapshot output directory (must be under prompt-dsl-system/tools)",
    )
    apply_move_p.add_argument("--snapshot-label", default="apply-move", help="Optional snapshot label")
    apply_move_p.add_argument("--verify-gate", default="", help="true/false, policy default if omitted")
    apply_move_p.add_argument("--verify-threshold", default="FAIL", help="PASS|WARN|FAIL, default FAIL")
    apply_move_p.add_argument(
        "--verify-report",
        default="prompt-dsl-system/tools/followup_verify_report.json",
        help="Follow-up verify report path (must be under prompt-dsl-system/tools)",
    )
    apply_move_p.add_argument("--verify-refresh", default="false", help="true/false, default false")
    apply_move_p.add_argument(
        "--output-dir",
        default="prompt-dsl-system/tools",
        help="Output directory for guard/plan artifacts (must be under prompt-dsl-system/tools)",
    )
    apply_move_p.add_argument("--recheck", default="true", help="true/false, default true")
    apply_move_p.set_defaults(func=cmd_apply_move)

    resolve_conflict_p = sub.add_parser(
        "resolve-move-conflicts",
        help="Plan/apply conflict resolution strategies for move dst collisions",
    )
    resolve_conflict_p.add_argument("--repo-root", default=".", help="Repository root path")
    resolve_conflict_p.add_argument("--module-path", required=True, help="Module boundary path")
    resolve_conflict_p.add_argument(
        "--output-dir",
        default="prompt-dsl-system/tools",
        help="Output directory for conflict plan artifacts (must be under prompt-dsl-system/tools)",
    )
    resolve_conflict_p.add_argument("--mode", choices=["plan", "apply"], default="plan")
    resolve_conflict_p.add_argument(
        "--strategy",
        choices=["rename_suffix", "imports_bucket", "abort"],
        default="abort",
    )
    resolve_conflict_p.add_argument("--yes", action="store_true", help="Required for mode=apply")
    resolve_conflict_p.add_argument("--dry-run", default="true", help="true/false, default true")
    resolve_conflict_p.add_argument("--ack", help="Risk gate ACK token")
    resolve_conflict_p.add_argument("--ack-file", help="Risk gate token json file")
    resolve_conflict_p.add_argument("--ack-latest", action="store_true", help="Use latest token from output-dir")
    resolve_conflict_p.add_argument("--risk-threshold", default="HIGH")
    resolve_conflict_p.add_argument("--context-id", help="Optional context id for trace history")
    resolve_conflict_p.add_argument("--trace-id", help="Optional trace id for trace history")
    resolve_conflict_p.add_argument("--snapshot", default="", help="true/false, policy default if omitted")
    resolve_conflict_p.add_argument("--no-snapshot", action="store_true", help="Disable pre-apply snapshot")
    resolve_conflict_p.add_argument(
        "--snapshot-dir",
        default="",
        help="Snapshot output directory (must be under prompt-dsl-system/tools)",
    )
    resolve_conflict_p.add_argument(
        "--snapshot-label",
        default="resolve-move-conflicts",
        help="Optional snapshot label",
    )
    resolve_conflict_p.set_defaults(func=cmd_resolve_move_conflicts)

    scan_followup_p = sub.add_parser(
        "scan-followup",
        help="Generate static follow-up checklist from move mappings",
    )
    scan_followup_p.add_argument("--repo-root", default=".", help="Repository root path")
    scan_followup_p.add_argument("--moves", required=True, help="Moves json (mapping/move_report/conflict_plan)")
    scan_followup_p.add_argument(
        "--output-dir",
        default="prompt-dsl-system/tools",
        help="Output directory for follow-up scan artifacts (must be under prompt-dsl-system/tools)",
    )
    scan_followup_p.add_argument("--mode", choices=["plan", "apply"], default="plan")
    scan_followup_p.add_argument("--max-hits-per-move", default="50")
    scan_followup_p.set_defaults(func=cmd_scan_followup)

    apply_followup_p = sub.add_parser(
        "apply-followup-fixes",
        help="Generate/apply conservative follow-up replacement patch from scan report",
    )
    apply_followup_p.add_argument("--repo-root", default=".", help="Repository root path")
    apply_followup_p.add_argument("--module-path", help="Optional module boundary path for verify-refresh")
    apply_followup_p.add_argument("--scan-report", required=True, help="followup_scan_report*.json path")
    apply_followup_p.add_argument(
        "--output-dir",
        default="prompt-dsl-system/tools",
        help="Output directory for patch artifacts (must be under prompt-dsl-system/tools)",
    )
    apply_followup_p.add_argument("--mode", choices=["plan", "apply"], default="plan")
    apply_followup_p.add_argument("--yes", action="store_true")
    apply_followup_p.add_argument("--dry-run", default="true")
    apply_followup_p.add_argument("--max-changes", default="100")
    apply_followup_p.add_argument(
        "--confidence-threshold", choices=["low", "medium", "high"], default="high"
    )
    apply_followup_p.add_argument("--include-ext", action="append", default=[])
    apply_followup_p.add_argument("--exclude-path", action="append", default=[])
    apply_followup_p.add_argument("--ack", help="Risk gate ACK token")
    apply_followup_p.add_argument("--ack-file", help="Risk gate token json file")
    apply_followup_p.add_argument("--ack-latest", action="store_true", help="Use latest token from output-dir")
    apply_followup_p.add_argument("--ack-source", help=argparse.SUPPRESS)
    apply_followup_p.add_argument("--ack-note", help="Optional rationale note when ACK is used under verify FAIL")
    apply_followup_p.add_argument("--context-id", help="Optional context id for trace history")
    apply_followup_p.add_argument("--trace-id", help="Optional trace id for trace history")
    apply_followup_p.add_argument("--snapshot", default="", help="true/false, policy default if omitted")
    apply_followup_p.add_argument("--no-snapshot", action="store_true", help="Disable pre-apply snapshot")
    apply_followup_p.add_argument(
        "--snapshot-dir",
        default="",
        help="Snapshot output directory (must be under prompt-dsl-system/tools)",
    )
    apply_followup_p.add_argument(
        "--snapshot-label",
        default="apply-followup-fixes",
        help="Optional snapshot label",
    )
    apply_followup_p.add_argument("--risk-threshold", default="HIGH")
    apply_followup_p.add_argument("--verify-gate", default="", help="true/false, policy default if omitted")
    apply_followup_p.add_argument("--verify-threshold", default="FAIL", help="PASS|WARN|FAIL, default FAIL")
    apply_followup_p.add_argument(
        "--verify-report",
        default="prompt-dsl-system/tools/followup_verify_report.json",
        help="Follow-up verify report path (must be under prompt-dsl-system/tools)",
    )
    apply_followup_p.add_argument("--verify-refresh", default="false", help="true/false, default false")
    apply_followup_p.set_defaults(func=cmd_apply_followup_fixes)

    verify_followup_p = sub.add_parser(
        "verify-followup-fixes",
        help="Verify residual old-reference tokens after move/patch operations (read-only)",
    )
    verify_followup_p.add_argument("--repo-root", default=".", help="Repository root path")
    verify_followup_p.add_argument("--moves", required=True, help="moves json path")
    verify_followup_p.add_argument("--scan-report", help="optional followup scan report path")
    verify_followup_p.add_argument("--patch-plan", help="optional followup patch plan path")
    verify_followup_p.add_argument(
        "--output-dir",
        default="prompt-dsl-system/tools",
        help="Output directory for verify artifacts (must be under prompt-dsl-system/tools)",
    )
    verify_followup_p.add_argument("--mode", choices=["post-move", "post-patch", "full"], default="full")
    verify_followup_p.add_argument("--max-hits", default="200")
    verify_followup_p.add_argument("--use-rg", default="true")
    verify_followup_p.add_argument("--exclude-dir", action="append", default=[])
    verify_followup_p.add_argument("--include-ext", action="append", default=[])
    verify_followup_p.set_defaults(func=cmd_verify_followup_fixes)

    snapshot_restore_p = sub.add_parser(
        "snapshot-restore-guide",
        help="Generate restore guide and restore scripts from a snapshot directory",
    )
    snapshot_restore_p.add_argument("--repo-root", default=".", help="Repository root path")
    snapshot_restore_p.add_argument("--snapshot", required=True, help="Snapshot directory path")
    snapshot_restore_p.add_argument(
        "--output-dir",
        default="",
        help="Output directory for restore artifacts (default: <snapshot>/restore)",
    )
    snapshot_restore_p.add_argument("--shell", choices=["bash", "zsh"], default="bash")
    snapshot_restore_p.add_argument("--mode", choices=["generate", "check"], default="generate")
    snapshot_restore_p.add_argument("--strict", default="true", help="true/false, default true")
    snapshot_restore_p.add_argument("--no-strict", action="store_true", help="Disable strict repo-root match check")
    snapshot_restore_p.add_argument("--dry-run", default="true", help="true/false, default true")
    snapshot_restore_p.set_defaults(func=cmd_snapshot_restore_guide)

    snapshot_prune_p = sub.add_parser(
        "snapshot-prune",
        help="Prune tools snapshots with auditable policy (default dry-run)",
    )
    snapshot_prune_p.add_argument("--repo-root", default=".", help="Repository root path")
    snapshot_prune_p.add_argument(
        "--snapshots-dir",
        default="",
        help="Snapshots directory (must be under prompt-dsl-system/tools)",
    )
    snapshot_prune_p.add_argument("--keep-last", default="")
    snapshot_prune_p.add_argument("--max-total-size-mb", default="")
    snapshot_prune_p.add_argument("--only-label", action="append", default=[])
    snapshot_prune_p.add_argument("--exclude-label", action="append", default=[])
    snapshot_prune_p.add_argument("--dry-run", default="")
    snapshot_prune_p.add_argument("--apply", action="store_true")
    snapshot_prune_p.add_argument(
        "--output-dir",
        default="",
        help="Output directory for prune reports (must be under prompt-dsl-system/tools)",
    )
    snapshot_prune_p.add_argument("--now", default="")
    snapshot_prune_p.set_defaults(func=cmd_snapshot_prune)

    snapshot_index_p = sub.add_parser(
        "snapshot-index",
        help="Build snapshot index for tools/snapshots",
    )
    snapshot_index_p.add_argument("--repo-root", default=".", help="Repository root path")
    snapshot_index_p.add_argument(
        "--snapshots-dir",
        default="",
        help="Snapshots directory (must be under prompt-dsl-system/tools)",
    )
    snapshot_index_p.add_argument(
        "--output-dir",
        default="",
        help="Output directory for index files (must be under prompt-dsl-system/tools)",
    )
    snapshot_index_p.add_argument("--limit", default="")
    snapshot_index_p.add_argument("--include-invalid", default="")
    snapshot_index_p.add_argument("--now", default="")
    snapshot_index_p.set_defaults(func=cmd_snapshot_index)

    snapshot_open_p = sub.add_parser(
        "snapshot-open",
        help="Locate best snapshot by trace/snapshot/context/label filters",
    )
    snapshot_open_p.add_argument("--repo-root", default=".", help="Repository root path")
    snapshot_open_p.add_argument(
        "--index",
        default="",
        help="Snapshot index json path (must be under prompt-dsl-system/tools)",
    )
    snapshot_open_p.add_argument(
        "--snapshots-dir",
        default="",
        help="Snapshots directory (used for auto index build)",
    )
    snapshot_open_p.add_argument("--trace-id")
    snapshot_open_p.add_argument("--snapshot-id")
    snapshot_open_p.add_argument("--context-id")
    snapshot_open_p.add_argument("--label")
    snapshot_open_p.add_argument("--latest", default="true")
    snapshot_open_p.add_argument("--output", choices=["json", "text", "md"], default="text")
    snapshot_open_p.add_argument("--emit-restore-guide", default="false")
    snapshot_open_p.set_defaults(func=cmd_snapshot_open)

    trace_index_p = sub.add_parser(
        "trace-index",
        help="Build trace index from trace history + deliveries + snapshots",
    )
    trace_index_p.add_argument("--repo-root", default=".", help="Repository root path")
    trace_index_p.add_argument("--tools-dir", default="")
    trace_index_p.add_argument("--trace-history", default="")
    trace_index_p.add_argument("--deliveries-dir", default="")
    trace_index_p.add_argument("--snapshots-dir", default="")
    trace_index_p.add_argument("--output-dir", default="")
    trace_index_p.add_argument("--window", default="")
    trace_index_p.add_argument("--scan-all", default="")
    trace_index_p.add_argument("--limit-md", default="")
    trace_index_p.set_defaults(func=cmd_trace_index)

    trace_open_p = sub.add_parser(
        "trace-open",
        help="Open trace chain by trace-id (supports prefix match)",
    )
    trace_open_p.add_argument("--repo-root", default=".", help="Repository root path")
    trace_open_p.add_argument("--tools-dir", default="")
    trace_open_p.add_argument("--index", default="")
    trace_open_p.add_argument("--trace-id", required=True)
    trace_open_p.add_argument("--output", choices=["text", "json", "md"], default="text")
    trace_open_p.add_argument("--emit-restore", default="true")
    trace_open_p.add_argument("--emit-verify", default="true")
    trace_open_p.add_argument("--latest", default="true")
    trace_open_p.set_defaults(func=cmd_trace_open)

    trace_diff_p = sub.add_parser(
        "trace-diff",
        help="Compare two traces (A/B) from trace index and emit diff reports",
    )
    trace_diff_p.add_argument("--repo-root", default=".", help="Repository root path")
    trace_diff_p.add_argument("--tools-dir", default="")
    trace_diff_p.add_argument("--index", default="")
    trace_diff_p.add_argument("--a", required=True, help="Trace A id or prefix")
    trace_diff_p.add_argument("--b", required=True, help="Trace B id or prefix")
    trace_diff_p.add_argument("--latest", default="true")
    trace_diff_p.add_argument(
        "--output-dir",
        default="",
        help="Output directory for diff reports (must be under prompt-dsl-system/tools)",
    )
    trace_diff_p.add_argument("--scan-deliveries", default="")
    trace_diff_p.add_argument("--deliveries-depth", default="")
    trace_diff_p.add_argument("--limit-files", default="")
    trace_diff_p.add_argument("--format", choices=["md", "json", "both"], default="both")
    trace_diff_p.set_defaults(func=cmd_trace_diff)

    trace_bisect_p = sub.add_parser(
        "trace-bisect",
        help="Generate shortest PASS->FAIL bisect troubleshooting plan",
    )
    trace_bisect_p.add_argument("--repo-root", default=".", help="Repository root path")
    trace_bisect_p.add_argument("--tools-dir", default="")
    trace_bisect_p.add_argument("--index", default="")
    trace_bisect_p.add_argument("--bad", required=True, help="Bad trace id or prefix")
    trace_bisect_p.add_argument("--good", default="", help="Good trace id or prefix")
    trace_bisect_p.add_argument("--auto-find-good", default="")
    trace_bisect_p.add_argument(
        "--verify-top",
        default="PASS",
        choices=["PASS", "WARN", "FAIL", "MISSING"],
        help="verify_top filter used when auto-selecting good trace",
    )
    trace_bisect_p.add_argument(
        "--output-dir",
        default="",
        help="Output directory for bisect plan files (must be under prompt-dsl-system/tools)",
    )
    trace_bisect_p.add_argument("--max-steps", default="")
    trace_bisect_p.add_argument("--emit-sh", default="true")
    trace_bisect_p.add_argument("--emit-md", default="true")
    trace_bisect_p.set_defaults(func=cmd_trace_bisect)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
