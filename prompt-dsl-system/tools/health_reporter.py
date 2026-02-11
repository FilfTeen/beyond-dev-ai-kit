#!/usr/bin/env python3
"""Aggregate orchestration-system health from validate/trace/loop/verify signals.

Standard-library only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from policy_loader import build_cli_override_dict, get_policy_value, load_policy

DEFAULT_VALIDATE_REPORT = "prompt-dsl-system/tools/validate_report.json"
DEFAULT_TRACE_HISTORY = "prompt-dsl-system/tools/trace_history.jsonl"
DEFAULT_OUTPUT_DIR = "prompt-dsl-system/tools"
SKILLS_JSON = "prompt-dsl-system/05_skill_registry/skills.json"
LOOP_DETECTOR = "prompt-dsl-system/tools/loop_detector.py"


def parse_bool(value: Any, default: bool = False) -> bool:
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


def parse_int(value: Any, default: int, minimum: int = 1) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if n < minimum:
        return minimum
    return n


def now_iso(timezone_mode: str = "local") -> str:
    tz_mode = str(timezone_mode or "local").strip().lower()
    now = datetime.now().astimezone()
    if tz_mode in {"utc", "z"}:
        now = now.astimezone(timezone.utc)
    return now.replace(microsecond=0).isoformat()


def parse_timestamp(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_repo_path(repo_root: Path, raw_path: str) -> Path:
    p = Path(raw_path)
    if not p.is_absolute():
        p = (repo_root / p).resolve()
    else:
        p = p.resolve()
    return p


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def normalize_text(value: Any, fallback: str = "unknown", none_as_missing: bool = True) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    if none_as_missing and text.lower() == "none":
        return fallback
    return text


def counter_to_sorted_dict(counter: Counter) -> Dict[str, int]:
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return {k: int(v) for k, v in items}


def load_version_distribution(repo_root: Path) -> Tuple[Counter, int]:
    versions: Counter = Counter()
    total = 0
    skills_path = (repo_root / SKILLS_JSON).resolve()
    if not skills_path.exists() or not skills_path.is_file():
        return versions, total
    try:
        data = json.loads(skills_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return versions, total
    if not isinstance(data, list):
        return versions, total
    for item in data:
        if not isinstance(item, dict):
            continue
        total += 1
        versions[normalize_text(item.get("version"), fallback="unknown")] += 1
    return versions, total


def infer_validate_status(errors: int, warnings: int) -> str:
    if errors > 0:
        return "FAIL"
    if warnings > 0:
        return "WARN"
    return "PASS"


def collect_trace_files(
    repo_root: Path,
    trace_history: Path,
    include_deliveries: bool,
) -> List[Path]:
    discovered: List[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path.resolve())
        if key in seen:
            return
        seen.add(key)
        discovered.append(path.resolve())

    add(trace_history)
    if include_deliveries:
        for base in [
            repo_root / "prompt-dsl-system" / "tools" / "deliveries",
            repo_root / "deliveries",
        ]:
            if not base.exists() or not base.is_dir():
                continue
            for item in base.rglob("trace_history.jsonl"):
                add(item)

    return discovered


def load_trace_records(trace_files: Sequence[Path]) -> Tuple[List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    records: List[Dict[str, Any]] = []
    seq = 0

    for path in trace_files:
        if not path.exists() or not path.is_file():
            warnings.append(f"trace history missing: {path}")
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            warnings.append(f"failed to read trace history {path}: {exc}")
            continue
        for line_no, raw in enumerate(lines, start=1):
            text = raw.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except json.JSONDecodeError:
                warnings.append(f"invalid trace JSON at {path}:{line_no}")
                continue
            if not isinstance(item, dict):
                warnings.append(f"non-object trace record at {path}:{line_no}")
                continue
            seq += 1
            row = dict(item)
            row["_source"] = str(path)
            row["_line"] = line_no
            row["_seq"] = seq
            row["_ts"] = parse_timestamp(row.get("timestamp"))
            records.append(row)

    records.sort(key=lambda r: (r["_ts"] is None, r["_ts"] or datetime.min.replace(tzinfo=timezone.utc), r["_seq"]))
    return records, warnings


def detect_bypass_attempt_count(records: Sequence[Dict[str, Any]]) -> int:
    count = 0
    push_commands = {"run", "apply-move", "apply-followup-fixes"}
    for rec in records:
        command = normalize_text(rec.get("command"), fallback="", none_as_missing=True).lower()
        verify_status = normalize_text(rec.get("verify_status"), fallback="MISSING").upper()
        verify_gate_required = parse_bool(rec.get("verify_gate_required"), default=False)
        blocked_by = normalize_text(rec.get("blocked_by"), fallback="none", none_as_missing=False)
        ack_used = normalize_text(rec.get("ack_used"), fallback="none", none_as_missing=False)

        if command not in push_commands:
            continue
        if verify_status != "FAIL":
            continue
        if not verify_gate_required:
            continue
        if blocked_by != "verify_gate" or ack_used != "none":
            count += 1
    return count


def run_loop_summary(
    repo_root: Path,
    output_dir: Path,
    recent_records: Sequence[Dict[str, Any]],
    window: int,
) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    if not recent_records:
        return {"level": "NONE", "triggers": []}, warnings

    detector = (repo_root / LOOP_DETECTOR).resolve()
    if not detector.exists():
        warnings.append(f"loop detector missing: {detector}")
        return {"level": "NONE", "triggers": []}, warnings

    latest = recent_records[-1]
    pipeline_path = latest.get("pipeline_path")
    module_path = latest.get("effective_module_path")

    with tempfile.TemporaryDirectory(prefix="health_loop_", dir=str(output_dir)) as tmp:
        tmp_dir = Path(tmp)
        history_file = tmp_dir / "trace_window.jsonl"
        out_dir = tmp_dir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        with history_file.open("w", encoding="utf-8") as f:
            for rec in recent_records:
                clone = {k: v for k, v in rec.items() if not str(k).startswith("_")}
                f.write(json.dumps(clone, ensure_ascii=False) + "\n")

        cmd = [
            sys.executable,
            str(detector),
            "--repo-root",
            str(repo_root),
            "--history",
            str(history_file),
            "--window",
            str(max(2, min(window, len(recent_records)))),
            "--same-trace-only",
            "false",
            "--output-dir",
            str(out_dir),
        ]
        if isinstance(pipeline_path, str) and pipeline_path.strip():
            cmd.extend(["--pipeline-path", pipeline_path.strip()])
        if isinstance(module_path, str) and module_path.strip():
            cmd.extend(["--effective-module-path", module_path.strip()])

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            if proc.stderr.strip():
                warnings.append(f"loop detector stderr: {proc.stderr.strip()}")
            warnings.append(f"loop detector failed with exit={proc.returncode}")
            return {"level": "NONE", "triggers": []}, warnings

        diag_path = out_dir / "loop_diagnostics.json"
        if not diag_path.exists():
            warnings.append("loop detector output missing: loop_diagnostics.json")
            return {"level": "NONE", "triggers": []}, warnings
        diag = safe_read_json(diag_path)
        if not diag:
            warnings.append("loop detector output unreadable")
            return {"level": "NONE", "triggers": []}, warnings
        return diag, warnings


def build_recommendations(
    validate_errors: int,
    validate_warnings: int,
    trace_total: int,
    verify_fail_count: int,
    exit4_count: int,
    bypass_attempt_count: int,
    guard_gate_blocks: int,
) -> List[str]:
    recs: List[str] = []
    if validate_errors > 0:
        recs.append(
            f"Fix validate errors first ({validate_errors}); prioritize registry/path parity before any promotion."
        )
    if validate_warnings > 0 and validate_errors == 0:
        recs.append(
            f"Clear validate warnings ({validate_warnings}) to keep orchestration baseline deterministic."
        )
    if verify_fail_count > 0:
        recs.append(
            f"Verify is failing in recent traces ({verify_fail_count}); run verify-followup-fixes and keep verify-gate=true."
        )
    if exit4_count > 0 and trace_total > 0:
        ratio = float(exit4_count) / float(trace_total)
        recs.append(
            f"Risk-gate blocks are frequent (exit 4: {exit4_count}/{trace_total}, {ratio:.0%}); reduce forbidden/outside-module triggers before retry."
        )
    if bypass_attempt_count >= 1:
        recs.append(
            f"Bypass attempts detected ({bypass_attempt_count}); stop push commands, resolve verify FAIL to PASS, and document rationale via --ack-note when exception is necessary."
        )
    if guard_gate_blocks > 0:
        recs.append(
            f"Guard-gate blocks observed ({guard_gate_blocks}); standardize -m/--module-path in all run/apply commands."
        )
    if trace_total == 0:
        recs.append(
            "No trace signals yet; run at least one guarded validate/run cycle to establish runtime telemetry."
        )

    if len(recs) < 3:
        defaults = [
            "Keep validate as a pre-flight gate for every orchestration change.",
            "Use debug-guard before run/apply to pre-generate move/rollback plans.",
            "Review health_report.json after each validate to catch trend regressions early.",
        ]
        for item in defaults:
            if item not in recs:
                recs.append(item)
            if len(recs) >= 3:
                break
    return recs[:7]


def format_counter(counter: Dict[str, int], empty_label: str = "none") -> str:
    if not counter:
        return empty_label
    return ", ".join(f"{k}={v}" for k, v in counter.items())


def write_markdown(path: Path, report: Dict[str, Any]) -> None:
    build = report["build_integrity"]
    signals = report["execution_signals"]
    risk = report["risk_triggers"]
    recs = report["recommended_next_actions"]

    version_top = build.get("skills_versions_top3", [])
    if version_top:
        version_text = ", ".join(f"{item['version']} x{item['count']}" for item in version_top)
    else:
        version_text = "none"

    lines: List[str] = []
    lines.append("# Health Report")
    lines.append(f"- Generated at: {report.get('generated_at')}")
    lines.append(f"- Repo root: {report.get('repo_root')}")
    lines.append(f"- Window: last {report.get('window')} traces")
    lines.append("")
    lines.append("## Build Integrity")
    lines.append(f"- Registry entries: {build.get('registry_entries', 0)}")
    lines.append(f"- Pipelines checked: {build.get('pipelines_checked', 0)}")
    lines.append(
        f"- Validate: {build.get('validate_status', 'UNKNOWN')} (errors={build.get('errors', 0)}, warnings={build.get('warnings', 0)})"
    )
    lines.append(f"- Skills versions: {version_text}")
    lines.append("")
    lines.append("## Execution Signals (last N)")
    lines.append(f"- Commands: {format_counter(signals.get('command_distribution', {}))}")
    lines.append(f"- Exit codes: {format_counter(signals.get('exit_code_distribution', {}))}")
    lines.append(f"- Blocked by: {format_counter(signals.get('blocked_by_distribution', {}))}")
    lines.append(f"- Verify status: {format_counter(signals.get('verify_status_distribution', {}))}")
    lines.append(f"- Ack usage: {format_counter(signals.get('ack_used_distribution', {}))}")
    lines.append("")
    lines.append("## Risk Triggers")
    lines.append("- Top triggers:")
    top_triggers = risk.get("top_triggers", [])
    if not top_triggers:
        lines.append("  1) none")
    else:
        for idx, item in enumerate(top_triggers[:10], start=1):
            lines.append(f"  {idx}) {item.get('id')} ({item.get('count')})")
    lines.append(f"- Bypass attempts: {risk.get('bypass_attempt_count', 0)}")
    lines.append("")
    lines.append("## Recommended Next Actions")
    for idx, rec in enumerate(recs, start=1):
        lines.append(f"{idx}) {rec}")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate orchestration-system health report")
    p.add_argument("--repo-root", required=True, help="Repository root")
    p.add_argument("--policy", default="", help="Optional policy YAML path")
    p.add_argument("--policy-override", action="append", default=[], help="Policy override key=value")
    p.add_argument("--validate-report", default="")
    p.add_argument("--trace-history", default="")
    p.add_argument("--window", default="")
    p.add_argument("--output-dir", default="")
    p.add_argument("--include-deliveries", default="false")
    p.add_argument("--use-rg", default="true")
    p.add_argument("--timezone", default="local")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        print(f"Invalid repo root: {repo_root}", file=sys.stderr)
        return 2

    policy_overrides = build_cli_override_dict(
        repo_root=repo_root,
        policy_path=str(getattr(args, "policy", "") or "").strip(),
        policy_override_exprs=getattr(args, "policy_override", []) or [],
    )
    policy = load_policy(repo_root, cli_overrides=policy_overrides)

    validate_report_default = str(get_policy_value(policy, "paths.validate_report", DEFAULT_VALIDATE_REPORT) or DEFAULT_VALIDATE_REPORT)
    trace_history_default = str(get_policy_value(policy, "paths.trace_history", DEFAULT_TRACE_HISTORY) or DEFAULT_TRACE_HISTORY)
    output_dir_default = str(get_policy_value(policy, "paths.tools_dir", DEFAULT_OUTPUT_DIR) or DEFAULT_OUTPUT_DIR)
    window_default = parse_int(get_policy_value(policy, "health.window", 20), default=20, minimum=1)

    validate_report_raw = str(args.validate_report or "").strip() or validate_report_default
    trace_history_raw = str(args.trace_history or "").strip() or trace_history_default
    output_dir_raw = str(args.output_dir or "").strip() or output_dir_default

    validate_report_path = to_repo_path(repo_root, validate_report_raw)
    trace_history_path = to_repo_path(repo_root, trace_history_raw)
    output_dir = to_repo_path(repo_root, output_dir_raw)
    output_dir.mkdir(parents=True, exist_ok=True)

    window = parse_int(args.window, default=window_default, minimum=1)
    include_deliveries = parse_bool(args.include_deliveries, default=False)
    use_rg = parse_bool(args.use_rg, default=True)
    timezone_mode = str(args.timezone or "local").strip() or "local"

    validate_report = safe_read_json(validate_report_path)
    registry_entries = int(
        (validate_report.get("registry") or {}).get("entry_count", 0)
        if isinstance(validate_report.get("registry"), dict)
        else 0
    )
    pipelines_checked = int(
        (validate_report.get("summary") or {}).get("pipelines_checked", 0)
        if isinstance(validate_report.get("summary"), dict)
        else 0
    )
    errors = int(
        (validate_report.get("summary") or {}).get("total_errors", 0)
        if isinstance(validate_report.get("summary"), dict)
        else 0
    )
    warnings = int(
        (validate_report.get("summary") or {}).get("total_warnings", 0)
        if isinstance(validate_report.get("summary"), dict)
        else 0
    )
    yaml_json_parity = None
    if isinstance(validate_report.get("summary"), dict):
        yaml_json_parity = validate_report["summary"].get("yaml_json_parity")
    if yaml_json_parity is None:
        yaml_json_parity = validate_report.get("yaml_json_parity")

    versions_counter, skills_total_from_registry = load_version_distribution(repo_root)
    if registry_entries <= 0:
        registry_entries = skills_total_from_registry

    trace_files = collect_trace_files(
        repo_root=repo_root,
        trace_history=trace_history_path,
        include_deliveries=include_deliveries,
    )
    trace_records, trace_warnings = load_trace_records(trace_files)
    recent = trace_records[-window:] if window > 0 else list(trace_records)

    cmd_counter: Counter = Counter()
    exit_counter: Counter = Counter()
    blocked_counter: Counter = Counter()
    verify_counter: Counter = Counter()
    ack_counter: Counter = Counter()
    overall_risk_counter: Counter = Counter()

    for rec in recent:
        cmd_counter[normalize_text(rec.get("command"), fallback="unknown", none_as_missing=True)] += 1
        exit_counter[normalize_text(rec.get("exit_code"), fallback="unknown")] += 1
        blocked_counter[normalize_text(rec.get("blocked_by"), fallback="none", none_as_missing=False)] += 1
        verify_counter[normalize_text(rec.get("verify_status"), fallback="MISSING").upper()] += 1
        ack_counter[normalize_text(rec.get("ack_used"), fallback="none", none_as_missing=False)] += 1
        if "overall_risk" in rec:
            overall_risk_counter[normalize_text(rec.get("overall_risk"), fallback="unknown").upper()] += 1

    bypass_attempt_count = detect_bypass_attempt_count(recent)
    loop_diag, loop_warnings = run_loop_summary(
        repo_root=repo_root,
        output_dir=output_dir,
        recent_records=recent,
        window=window,
    )
    trigger_counter: Counter = Counter()
    triggers_raw = loop_diag.get("triggers")
    if isinstance(triggers_raw, list):
        for item in triggers_raw:
            if isinstance(item, dict):
                trigger_id = normalize_text(item.get("id"), fallback="unknown")
            else:
                trigger_id = normalize_text(item, fallback="unknown")
            trigger_counter[trigger_id] += 1
    if bypass_attempt_count > 0:
        trigger_counter["release_gate_bypass_attempt"] = max(
            trigger_counter.get("release_gate_bypass_attempt", 0),
            bypass_attempt_count,
        )

    top_triggers = [
        {"id": key, "count": int(value)}
        for key, value in sorted(trigger_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    ]

    verify_fail_count = int(verify_counter.get("FAIL", 0))
    exit4_count = int(exit_counter.get("4", 0))
    guard_gate_blocks = int(blocked_counter.get("guard_gate", 0))
    recommendations = build_recommendations(
        validate_errors=errors,
        validate_warnings=warnings,
        trace_total=len(recent),
        verify_fail_count=verify_fail_count,
        exit4_count=exit4_count,
        bypass_attempt_count=bypass_attempt_count,
        guard_gate_blocks=guard_gate_blocks,
    )

    status = infer_validate_status(errors=errors, warnings=warnings)
    health_report: Dict[str, Any] = {
        "generated_at": now_iso(timezone_mode=timezone_mode),
        "repo_root": str(repo_root),
        "window": window,
        "timezone": timezone_mode,
        "build_integrity": {
            "validate_report": to_repo_relative(validate_report_path, repo_root),
            "registry_entries": registry_entries,
            "pipelines_checked": pipelines_checked,
            "errors": errors,
            "warnings": warnings,
            "validate_status": status,
            "yaml_json_parity": yaml_json_parity,
            "skills_versions": counter_to_sorted_dict(versions_counter),
            "skills_versions_top3": [
                {"version": version, "count": int(count)}
                for version, count in sorted(versions_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
            ],
        },
        "execution_signals": {
            "trace_history": to_repo_relative(trace_history_path, repo_root),
            "trace_files_considered": [to_repo_relative(p, repo_root) for p in trace_files if p.exists()],
            "window_records": len(recent),
            "total_runs": len(recent),
            "command_distribution": counter_to_sorted_dict(cmd_counter),
            "exit_code_distribution": counter_to_sorted_dict(exit_counter),
            "blocked_by_distribution": counter_to_sorted_dict(blocked_counter),
            "verify_status_distribution": counter_to_sorted_dict(verify_counter),
            "ack_used_distribution": counter_to_sorted_dict(ack_counter),
            "overall_risk_distribution": counter_to_sorted_dict(overall_risk_counter),
            "risk_proxy": {
                "verify_fail_count": verify_fail_count,
                "exit4_count": exit4_count,
                "guard_gate_blocks": guard_gate_blocks,
                "risk_gate_blocks": int(blocked_counter.get("risk_gate", 0)),
                "verify_gate_blocks": int(blocked_counter.get("verify_gate", 0)),
                "loop_gate_blocks": int(blocked_counter.get("loop_gate", 0)),
            },
        },
        "risk_triggers": {
            "loop_level": normalize_text(loop_diag.get("level"), fallback="NONE").upper(),
            "top_triggers": top_triggers,
            "bypass_attempt_count": bypass_attempt_count,
        },
        "recommended_next_actions": recommendations,
        "sources": {
            "include_deliveries": include_deliveries,
            "use_rg": use_rg,
            "trace_load_warnings": trace_warnings,
            "loop_summary_warnings": loop_warnings,
        },
    }

    json_path = (output_dir / "health_report.json").resolve()
    md_path = (output_dir / "health_report.md").resolve()
    json_path.write_text(json.dumps(health_report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(md_path, health_report)

    print(f"health_report_json: {to_repo_relative(json_path, repo_root)}")
    print(f"health_report_md: {to_repo_relative(md_path, repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
