#!/usr/bin/env python3
"""Lightweight YAML parser and pipeline markdown extractor.

Extracted from pipeline_runner.py for modularity.
Standard-library only — no third-party dependencies.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


class ParseError(Exception):
    """Raised when a YAML block cannot be parsed with lightweight parser."""


def count_indent(line: str) -> int:
    """Return the number of leading spaces in *line*."""
    return len(line) - len(line.lstrip(" "))


def unquote(value: str) -> str:
    """Strip matching quotes from *value* and process escape sequences."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        inner = value[1:-1]
        if value[0] == '"':
            inner = inner.replace(r'\"', '"').replace(r"\\", "\\")
        else:
            inner = inner.replace(r"\'", "'").replace(r"\\", "\\")
        return inner
    return value


def split_top_level(text: str, delimiter: str = ",") -> List[str]:
    """Split *text* by *delimiter* respecting quotes and bracket nesting."""
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
    """Split a YAML key-value pair at the first top-level colon."""
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
    """Parse a YAML scalar string into its Python type (bool, int, float, list, None, or str)."""
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
    """Coerce *value* to bool using common CLI true/false synonyms."""
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
    """Remove trailing ``# comment`` from *value*, respecting quoted strings."""
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
    """Parse a two-level YAML document (top-level keys + one level of nesting)."""
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


def parse_inline_parameters(body: str) -> Dict[str, Any]:
    """Parse inline parameter syntax ``{key: val, key2: val2}`` into a dict."""
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
    """Parse block-style YAML parameters starting at *start_idx* in *lines*."""
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
    """Parse a single YAML step block, extracting skill name and parameters."""
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
    """Extract all \`\`\`yaml fenced code blocks from markdown text."""
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
