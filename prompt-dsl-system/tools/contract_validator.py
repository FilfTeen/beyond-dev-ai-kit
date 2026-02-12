#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _schema_default_path() -> Path:
    tool_dir = Path(__file__).resolve().parent
    for name in ("contract_schema_v2.json", "contract_schema_v1.json"):
        candidate = tool_dir / name
        if candidate.is_file():
            return candidate
    return tool_dir / "contract_schema_v2.json"


def load_json_file(path: Path) -> Dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        loaded = json.loads(raw)
    except FileNotFoundError as exc:
        raise ValueError(f"schema_file_missing:{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"schema_json_invalid:{path}:{exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError("schema_root_must_be_object")
    return loaded


def _extract_lines(text: str, machine_names: List[str]) -> List[str]:
    out: List[str] = []
    prefixes = tuple(f"{name} " for name in machine_names)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(prefixes) or line in machine_names:
            out.append(line)
    return out


def _parse_machine_line(line: str, line_spec: Dict[str, Any]) -> Tuple[str, Dict[str, str]]:
    tokens = shlex.split(line)
    if not tokens:
        raise ValueError("empty_machine_line")

    line_type = tokens[0]
    fields: Dict[str, str] = {}
    positional_value = ""

    for tok in tokens[1:]:
        if "=" in tok:
            key, value = tok.split("=", 1)
            fields[key] = value
        elif not positional_value:
            positional_value = tok

    if line_spec.get("allow_positional_path") and "path" not in fields and positional_value:
        fields["path"] = positional_value

    return line_type, fields


def _validate_versions_triplet_from_json(payload: Dict[str, Any], required_keys: List[str]) -> Tuple[bool, str]:
    versions = payload.get("versions")
    if not isinstance(versions, dict):
        return False, "json_versions_missing"
    missing = [k for k in required_keys if k not in versions]
    if missing:
        return False, f"json_versions_missing_keys:{','.join(missing)}"
    return True, ""


def _validate_machine_line(
    line_type: str,
    fields: Dict[str, str],
    line_spec: Dict[str, Any],
    enums: Dict[str, Any],
) -> Tuple[bool, str, str]:
    required_fields = line_spec.get("required_fields", [])
    if not isinstance(required_fields, list):
        return False, "schema_invalid", f"{line_type}:required_fields_not_list"

    missing_fields = [name for name in required_fields if not fields.get(name)]
    if missing_fields:
        return False, "missing_field", f"{line_type}:missing={','.join(missing_fields)}"

    require_versions_triplet = bool(line_spec.get("require_versions_triplet", True))
    if require_versions_triplet:
        if "package_version" not in fields or "plugin_version" not in fields or "contract_version" not in fields:
            return False, "missing_versions_triplet", f"{line_type}:missing_package_plugin_contract"

    json_spec = line_spec.get("json_payload", {})
    if not isinstance(json_spec, dict):
        return False, "schema_invalid", f"{line_type}:json_payload_not_object"

    payload: Dict[str, Any] | None = None
    payload_text = fields.get("json", "")

    if payload_text:
        if "\n" in payload_text or "\r" in payload_text:
            return False, "json_payload_newline", f"{line_type}:json_contains_newline"
        try:
            payload_loaded = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            return False, "json_parse_error", f"{line_type}:json_parse_error:{exc}"
        if not isinstance(payload_loaded, dict):
            return False, "json_payload_not_object", f"{line_type}:json_payload_not_object"
        payload = payload_loaded

        json_required_keys = json_spec.get("required_keys", [])
        if isinstance(json_required_keys, list):
            missing_json_keys = [k for k in json_required_keys if k not in payload]
            if missing_json_keys:
                return False, "json_missing_key", f"{line_type}:json_missing={','.join(missing_json_keys)}"

        versions_required_keys = json_spec.get("versions_required_keys", [])
        if isinstance(versions_required_keys, list) and versions_required_keys:
            ok, msg = _validate_versions_triplet_from_json(payload, versions_required_keys)
            if not ok:
                return False, "json_versions_invalid", f"{line_type}:{msg}"
    elif bool(json_spec.get("required", False)):
        return False, "json_payload_missing", f"{line_type}:json_payload_required"

    mismatch_enum = set(x for x in enums.get("mismatch_reason", []) if isinstance(x, str))
    reason_field = fields.get("mismatch_reason", "")
    if reason_field and reason_field != "-" and mismatch_enum and reason_field not in mismatch_enum:
        return False, "enum_violation", f"{line_type}:mismatch_reason={reason_field}"

    if payload is not None:
        payload_reason = payload.get("mismatch_reason")
        if isinstance(payload_reason, str) and payload_reason not in {"", "-"} and mismatch_enum and payload_reason not in mismatch_enum:
            return False, "enum_violation", f"{line_type}:json.mismatch_reason={payload_reason}"

    return True, "", ""


def _validate_additive_policy(
    current_schema: Dict[str, Any],
    baseline_schema: Dict[str, Any],
) -> Tuple[bool, str, str]:
    current_lines = current_schema.get("machine_lines", {})
    baseline_lines = baseline_schema.get("machine_lines", {})
    if not isinstance(current_lines, dict) or not isinstance(baseline_lines, dict):
        return False, "schema_invalid", "machine_lines_must_be_object"

    for line_name, baseline_spec in baseline_lines.items():
        if line_name not in current_lines:
            return False, "additive_violation", f"line_removed:{line_name}"
        if not isinstance(baseline_spec, dict) or not isinstance(current_lines.get(line_name), dict):
            return False, "schema_invalid", f"line_spec_invalid:{line_name}"

        baseline_required = baseline_spec.get("required_fields", [])
        current_required = current_lines[line_name].get("required_fields", [])
        if not isinstance(baseline_required, list) or not isinstance(current_required, list):
            return False, "schema_invalid", f"required_fields_not_list:{line_name}"

        missing = sorted(set(str(x) for x in baseline_required) - set(str(x) for x in current_required))
        if missing:
            return False, "additive_violation", f"required_fields_removed:{line_name}:{','.join(missing)}"

    return True, "", ""


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="contract_validator.py",
        description="Validate Hongzhi machine-line output against contract schema (zero dependencies).",
    )
    parser.add_argument(
        "--schema",
        default=str(_schema_default_path()),
        help=(
            "Path to contract schema JSON "
            "(default: auto-detect highest available, prefers contract_schema_v2.json then v1)"
        ),
    )
    parser.add_argument("--file", default=None, help="Path to log file to validate")
    parser.add_argument("--stdin", action="store_true", help="Read log text from stdin")
    parser.add_argument(
        "--baseline-schema",
        default=None,
        help="Optional baseline schema JSON for additive-only required_fields guard",
    )

    args = parser.parse_args()

    try:
        schema = load_json_file(Path(args.schema).expanduser().resolve())
    except ValueError as exc:
        print(f'CONTRACT_OK=0 CONTRACT_ERR=schema_load_failed CONTRACT_MSG={json.dumps(str(exc), ensure_ascii=False)}')
        return 2

    if args.baseline_schema:
        try:
            baseline = load_json_file(Path(args.baseline_schema).expanduser().resolve())
        except ValueError as exc:
            print(f'CONTRACT_OK=0 CONTRACT_ERR=baseline_schema_load_failed CONTRACT_MSG={json.dumps(str(exc), ensure_ascii=False)}')
            return 2
        ok, err, msg = _validate_additive_policy(schema, baseline)
        if not ok:
            print(f'CONTRACT_OK=0 CONTRACT_ERR={err} CONTRACT_MSG={json.dumps(msg, ensure_ascii=False)}')
            return 2

    machine_lines = schema.get("machine_lines", {})
    if not isinstance(machine_lines, dict) or not machine_lines:
        print('CONTRACT_OK=0 CONTRACT_ERR=schema_invalid CONTRACT_MSG="machine_lines_missing"')
        return 2

    if args.stdin:
        input_text = sys.stdin.read()
    elif args.file:
        try:
            input_text = Path(args.file).expanduser().resolve().read_text(encoding="utf-8")
        except OSError as exc:
            print(f'CONTRACT_OK=0 CONTRACT_ERR=input_read_failed CONTRACT_MSG={json.dumps(str(exc), ensure_ascii=False)}')
            return 2
    else:
        print('CONTRACT_OK=0 CONTRACT_ERR=input_missing CONTRACT_MSG="use --stdin or --file"')
        return 2

    line_names = list(machine_lines.keys())
    selected_lines = _extract_lines(input_text, line_names)
    if not selected_lines:
        print('CONTRACT_OK=0 CONTRACT_ERR=no_machine_lines CONTRACT_MSG="no known machine lines found"')
        return 2

    enums = schema.get("enums", {}) if isinstance(schema.get("enums"), dict) else {}

    checked = 0
    for raw_line in selected_lines:
        try:
            line_type, fields = _parse_machine_line(raw_line, machine_lines.get(raw_line.split()[0], {}))
        except Exception as exc:
            print(f'CONTRACT_OK=0 CONTRACT_ERR=parse_failed CONTRACT_MSG={json.dumps(str(exc), ensure_ascii=False)}')
            return 2

        line_spec = machine_lines.get(line_type)
        if not isinstance(line_spec, dict):
            continue

        ok, err, msg = _validate_machine_line(line_type, fields, line_spec, enums)
        if not ok:
            print(f'CONTRACT_OK=0 CONTRACT_ERR={err} CONTRACT_MSG={json.dumps(msg, ensure_ascii=False)}')
            return 2
        checked += 1

    if checked <= 0:
        print('CONTRACT_OK=0 CONTRACT_ERR=no_matching_lines CONTRACT_MSG="machine lines present but none matched schema"')
        return 2

    print(f"CONTRACT_OK=1 CONTRACT_LINES={checked} CONTRACT_SCHEMA={schema.get('schema_version', '-')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
