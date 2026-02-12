#!/usr/bin/env python3
"""Crash-resilience fuzz gate for pipeline parser and machine-line validator."""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

EXIT_FUZZ_FAIL = 53


def random_text(rng: random.Random, max_len: int = 240) -> str:
    alphabet = string.ascii_letters + string.digits + " \t\n:-_{}[](),./'\"#=`\\"
    size = rng.randint(0, max_len)
    return "".join(rng.choice(alphabet) for _ in range(size))


def random_word(rng: random.Random, min_len: int = 3, max_len: int = 12) -> str:
    alphabet = string.ascii_lowercase + string.digits + "_-"
    size = rng.randint(min_len, max_len)
    return "".join(rng.choice(alphabet) for _ in range(size))


def fuzz_pipeline_parser(pr: Any, rng: random.Random, iterations: int) -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "iterations": iterations,
        "yaml_blocks_seen": 0,
        "parse_errors_expected": 0,
        "crashes": 0,
        "structural_violations": 0,
        "crash_samples": [],
    }

    for idx in range(iterations):
        body = random_text(rng)
        if rng.random() < 0.40:
            body = (
                f"skill: skill_{random_word(rng)}\n"
                "parameters:\n"
                f"  mode: {random_word(rng)}\n"
                f"  objective: {random_word(rng)}\n"
            )
        elif rng.random() < 0.20:
            body = (
                f"skill: skill_{random_word(rng)}\n"
                "parameters: {mode: fuzz, objective: smoke, constraints: [scan-only]}\n"
            )

        markdown = f"{random_text(rng, 80)}\n```yaml\n{body}\n```\n{random_text(rng, 80)}"
        try:
            blocks = pr.extract_yaml_blocks(markdown)
            if not isinstance(blocks, list):
                stats["structural_violations"] += 1
                continue
            stats["yaml_blocks_seen"] += len(blocks)
            for block in blocks:
                content = str(block.get("content", ""))
                try:
                    parsed = pr.parse_yaml_step_block(content)
                except (pr.ParseError, ValueError):
                    stats["parse_errors_expected"] += 1
                    continue
                if not isinstance(parsed, dict):
                    stats["structural_violations"] += 1
                    continue
                if "skill" not in parsed or "parameters" not in parsed:
                    stats["structural_violations"] += 1
        except Exception as exc:  # pragma: no cover - crash capture branch
            stats["crashes"] += 1
            if len(stats["crash_samples"]) < 5:
                stats["crash_samples"].append(
                    {
                        "index": idx,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
    return stats


def build_contract_line(
    rng: random.Random,
    line_types: List[str],
    machine_lines: Dict[str, Any],
) -> str:
    if not line_types or rng.random() < 0.35:
        return random_text(rng, 220)

    line_type = rng.choice(line_types)
    spec = machine_lines.get(line_type, {})
    required_fields = spec.get("required_fields", []) if isinstance(spec, dict) else []
    fields: List[str] = []
    if isinstance(required_fields, list):
        for field_name in required_fields:
            key = str(field_name)
            if not key:
                continue
            if key == "json":
                payload = {"command": random_word(rng), "versions": {"package": "4.0.0", "plugin": "4.0.0", "contract": "4.0.0"}}
                fields.append(f"json={json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}")
            else:
                fields.append(f"{key}={random_word(rng)}")

    if rng.random() < 0.30:
        fields.append(f"mismatch_reason={random_word(rng)}")
    if rng.random() < 0.20:
        fields.append(random_word(rng))

    return " ".join([line_type] + fields)


def fuzz_contract_validator(cv: Any, rng: random.Random, iterations: int, schema_path: Path) -> Dict[str, Any]:
    schema = cv.load_json_file(schema_path)
    machine_lines = schema.get("machine_lines", {}) if isinstance(schema.get("machine_lines"), dict) else {}
    enums = schema.get("enums", {}) if isinstance(schema.get("enums"), dict) else {}
    line_types = [str(x) for x in machine_lines.keys()]

    stats: Dict[str, Any] = {
        "iterations": iterations,
        "parse_errors_expected": 0,
        "validated_lines": 0,
        "crashes": 0,
        "crash_samples": [],
    }

    for idx in range(iterations):
        line = build_contract_line(rng, line_types, machine_lines)
        tokens = line.split()
        first = tokens[0] if tokens else ""
        spec_hint = machine_lines.get(first, {}) if isinstance(machine_lines.get(first), dict) else {}
        try:
            line_type, fields = cv._parse_machine_line(line, spec_hint)
        except ValueError:
            stats["parse_errors_expected"] += 1
            continue
        except Exception as exc:  # pragma: no cover - crash capture branch
            stats["crashes"] += 1
            if len(stats["crash_samples"]) < 5:
                stats["crash_samples"].append(
                    {
                        "index": idx,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            continue

        line_spec = machine_lines.get(line_type)
        if not isinstance(line_spec, dict):
            continue
        try:
            _ok, _err, _msg = cv._validate_machine_line(line_type, fields, line_spec, enums)
            stats["validated_lines"] += 1
        except Exception as exc:  # pragma: no cover - crash capture branch
            stats["crashes"] += 1
            if len(stats["crash_samples"]) < 5:
                stats["crash_samples"].append(
                    {
                        "index": idx,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run parser/contract fuzz gate")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    parser.add_argument("--iterations", type=int, default=400, help="Fuzz iterations per target")
    parser.add_argument("--seed", type=int, default=20260212, help="Random seed")
    parser.add_argument("--out-json", default="", help="Optional output report path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[fuzz_gate] FAIL: invalid repo-root: {repo_root}")
        return 2
    if args.iterations < 50:
        print("[fuzz_gate] FAIL: iterations must be >= 50")
        return 2

    tools_dir = repo_root / "prompt-dsl-system" / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))

    try:
        import pipeline_runner as pr  # type: ignore
        import contract_validator as cv  # type: ignore
    except Exception as exc:
        print(f"[fuzz_gate] FAIL: import error: {type(exc).__name__}: {exc}")
        return 2

    schema_v2 = tools_dir / "contract_schema_v2.json"
    schema_v1 = tools_dir / "contract_schema_v1.json"
    schema_path = schema_v2 if schema_v2.is_file() else schema_v1
    if not schema_path.is_file():
        print("[fuzz_gate] FAIL: contract schema missing")
        return 2

    rng = random.Random(int(args.seed))
    pipeline_stats = fuzz_pipeline_parser(pr=pr, rng=rng, iterations=int(args.iterations))
    contract_stats = fuzz_contract_validator(cv=cv, rng=rng, iterations=int(args.iterations), schema_path=schema_path)

    crash_total = int(pipeline_stats["crashes"]) + int(contract_stats["crashes"])
    structural_violations = int(pipeline_stats["structural_violations"])
    passed = crash_total == 0 and structural_violations == 0

    report = {
        "tool": "fuzz_contract_pipeline_gate",
        "repo_root": str(repo_root),
        "seed": int(args.seed),
        "iterations_per_target": int(args.iterations),
        "passed": passed,
        "pipeline": pipeline_stats,
        "contract": contract_stats,
        "summary": {
            "crash_total": crash_total,
            "structural_violations": structural_violations,
        },
    }

    if args.out_json:
        out_path = Path(args.out_json).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if passed:
        print(
            "[fuzz_gate] PASS: "
            f"seed={args.seed} iterations={args.iterations} "
            f"crash_total={crash_total} structural_violations={structural_violations}"
        )
        return 0

    print("[fuzz_gate] FAIL")
    print(
        f"[fuzz_gate] summary: crash_total={crash_total} structural_violations={structural_violations}"
    )
    for sample in pipeline_stats.get("crash_samples", []):
        print(f"[fuzz_gate] pipeline_crash: {sample}")
    for sample in contract_stats.get("crash_samples", []):
        print(f"[fuzz_gate] contract_crash: {sample}")
    return EXIT_FUZZ_FAIL


if __name__ == "__main__":
    raise SystemExit(main())

