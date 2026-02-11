#!/usr/bin/env python3
"""Build shortest trace bisect troubleshooting plan (PASS -> FAIL)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from policy_loader import build_cli_override_dict, get_policy_value, load_policy


DEFAULT_TOOLS_DIR = "prompt-dsl-system/tools"
DEFAULT_INDEX_REL = "prompt-dsl-system/tools/trace_index.json"
TRACE_INDEXER_REL = "prompt-dsl-system/tools/trace_indexer.py"
PLACEHOLDERS_DEFAULT = [
    "MODULE_PATH",
    "PIPELINE_PATH",
    "MOVES_JSON",
    "SCAN_REPORT_JSON",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def parse_int(value: Any, default: int, minimum: int = 0) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if n < minimum:
        return minimum
    return n


def parse_iso8601(value: str) -> Optional[datetime]:
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


def to_path(raw: str, base: Path) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = (base / p).resolve()
    else:
        p = p.resolve()
    return p


def to_rel(path: Path, repo_root: Path) -> str:
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


def run_trace_indexer(repo_root: Path, tools_dir: Path, output_dir: Path) -> bool:
    script = (repo_root / TRACE_INDEXER_REL).resolve()
    if not script.exists():
        print(f"trace_indexer not found: {script}", file=sys.stderr)
        return False

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--tools-dir",
        str(tools_dir),
        "--output-dir",
        str(output_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode == 0


def match_trace(items: List[Dict[str, Any]], prefix: str, latest: bool = True) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    p = str(prefix or "").strip()
    matched: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        trace_id = str(item.get("trace_id") or "")
        if trace_id.startswith(p):
            matched.append(item)

    matched.sort(
        key=lambda it: parse_iso8601(str(it.get("last_seen_at") or ""))
        or datetime(1970, 1, 1, tzinfo=timezone.utc),
        reverse=True,
    )

    if not matched:
        return None, []
    if len(matched) > 1 and not latest:
        return None, matched
    return matched[0], matched


def count_values(commands: List[Dict[str, Any]], key: str, default: str = "") -> Dict[str, int]:
    counter: Counter[str] = Counter()
    for row in commands:
        if not isinstance(row, dict):
            continue
        counter[str(row.get(key) or default)] += 1
    return dict(counter)


def top_key(counts: Dict[str, int], default: str = "") -> str:
    if not counts:
        return default
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def latest_exit_code(commands: List[Dict[str, Any]], fallback: Any = None) -> Optional[int]:
    if commands:
        last = commands[-1] if isinstance(commands[-1], dict) else {}
        val = last.get("exit_code")
    else:
        val = fallback
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def has_run_exit0(commands: List[Dict[str, Any]]) -> bool:
    for row in commands:
        if not isinstance(row, dict):
            continue
        if str(row.get("command") or "") != "run":
            continue
        try:
            if int(row.get("exit_code")) == 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def summarize_trace(item: Dict[str, Any]) -> Dict[str, Any]:
    commands = item.get("commands") if isinstance(item.get("commands"), list) else []
    paths = item.get("paths") if isinstance(item.get("paths"), dict) else {}
    highlights = item.get("highlights") if isinstance(item.get("highlights"), dict) else {}

    blocked = count_values(commands, "blocked_by", default="none")
    verify = count_values(commands, "verify_status", default="MISSING")
    ack = count_values(commands, "ack_used", default="none")
    cmd_counts = count_values(commands, "command", default="unknown")

    v_top = str(highlights.get("latest_verify_status") or "")
    if not v_top:
        v_top = top_key(verify, default="MISSING")
    v_top = v_top.upper()

    latest_exit = latest_exit_code(commands, fallback=highlights.get("latest_exit_code"))
    bypass = highlights.get("bypass_attempt")
    if not isinstance(bypass, bool):
        bypass = False

    ack_total = sum(int(v) for k, v in ack.items() if str(k).lower() != "none")

    return {
        "trace_id": str(item.get("trace_id") or ""),
        "context_id": str(item.get("context_id") or ""),
        "last_seen_at": str(item.get("last_seen_at") or ""),
        "last_seen_dt": parse_iso8601(str(item.get("last_seen_at") or "")),
        "latest_exit_code": latest_exit,
        "latest_command": str(commands[-1].get("command") or "") if commands else "",
        "command_counts": cmd_counts,
        "blocked_by_counts": blocked,
        "verify_status_counts": verify,
        "ack_used_counts": ack,
        "ack_total": ack_total,
        "verify_top": v_top,
        "verify_fail_count": int(verify.get("FAIL", 0)),
        "has_run_exit0": has_run_exit0(commands),
        "bypass_attempt": bypass,
        "paths": {
            "deliveries_dir": paths.get("deliveries_dir") if isinstance(paths.get("deliveries_dir"), str) else None,
            "snapshot_paths": [str(x) for x in paths.get("snapshot_paths", []) if isinstance(x, str)]
            if isinstance(paths.get("snapshot_paths"), list)
            else [],
            "risk_gate_report": paths.get("risk_gate_report") if isinstance(paths.get("risk_gate_report"), str) else None,
            "verify_report": paths.get("verify_report") if isinstance(paths.get("verify_report"), str) else None,
            "health_report": paths.get("health_report") if isinstance(paths.get("health_report"), str) else None,
        },
        "raw_item": item,
    }


def choose_good_auto(
    items: List[Dict[str, Any]],
    bad: Dict[str, Any],
    verify_top: str,
) -> Optional[Dict[str, Any]]:
    bad_dt = bad.get("last_seen_dt")
    if not isinstance(bad_dt, datetime):
        return None

    verify_expected = str(verify_top or "PASS").strip().upper()
    candidates: List[Tuple[datetime, Dict[str, Any]]] = []

    for item in items:
        summary = summarize_trace(item)
        if summary.get("trace_id") == bad.get("trace_id"):
            continue

        ts = summary.get("last_seen_dt")
        if not isinstance(ts, datetime):
            continue
        if ts >= bad_dt:
            continue

        exit_code = summary.get("latest_exit_code")
        if exit_code != 0 and not summary.get("has_run_exit0"):
            continue

        if verify_expected and summary.get("verify_top") != verify_expected:
            continue

        candidates.append((ts, summary))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def diff_counts(a: Dict[str, int], b: Dict[str, int]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    keys = sorted(set(a.keys()) | set(b.keys()))
    for k in keys:
        delta = int(b.get(k, 0)) - int(a.get(k, 0))
        if delta != 0:
            out[k] = delta
    return out


def extract_placeholders(command: str) -> List[str]:
    found = re.findall(r"<([A-Z_][A-Z0-9_]*)>", command)
    # Preserve order but unique.
    seen: set[str] = set()
    out: List[str] = []
    for name in found:
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def add_step(
    steps: List[Dict[str, Any]],
    seen_commands: set[str],
    max_steps: int,
    purpose: str,
    when: str,
    command: str,
    expected: str,
    stop_if: str,
    risk: str,
) -> None:
    if len(steps) >= max_steps:
        return
    cmd_key = command.strip()
    if cmd_key in seen_commands:
        return
    seen_commands.add(cmd_key)
    step_id = f"S{len(steps)}"
    steps.append(
        {
            "id": step_id,
            "purpose": purpose,
            "when": when,
            "command": command,
            "expected": expected,
            "stop_if": stop_if,
            "risk": risk,
            "requires": extract_placeholders(command),
        }
    )


def build_plan_steps(
    good: Optional[Dict[str, Any]],
    bad: Dict[str, Any],
    signals: Dict[str, Any],
    max_steps: int,
) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    seen_commands: set[str] = set()

    good_trace = good.get("trace_id") if isinstance(good, dict) else None
    bad_trace = bad.get("trace_id")

    s0_good = good_trace if good_trace else "<GOOD_TRACE_ID>"
    add_step(
        steps,
        seen_commands,
        max_steps,
        purpose="Generate diff evidence",
        when="always",
        command=f"./prompt-dsl-system/tools/run.sh trace-diff -r . --a {s0_good} --b {bad_trace} --scan-deliveries false",
        expected="trace_diff.md generated with key deltas",
        stop_if="Diff shows verify FAIL spike or guard/loop gate increase",
        risk="none",
    )

    bypass = bool(signals.get("bypass_attempt", False))
    verify_changed = bool(signals.get("verify_changed", False))
    blocked_delta = signals.get("blocked_by_delta") if isinstance(signals.get("blocked_by_delta"), dict) else {}

    guard_delta = int(blocked_delta.get("guard_gate", 0)) + int(blocked_delta.get("outside_module", 0))
    loop_delta = int(blocked_delta.get("loop_gate", 0))
    verify_fail = str(bad.get("verify_top") or "MISSING").upper() == "FAIL" or int(bad.get("verify_fail_count", 0)) > int(
        good.get("verify_fail_count", 0) if isinstance(good, dict) else 0
    )

    bad_paths = bad.get("paths", {}) if isinstance(bad.get("paths"), dict) else {}
    has_snapshot = len(bad_paths.get("snapshot_paths") or []) > 0
    has_deliveries = bool(bad_paths.get("deliveries_dir"))

    # P0 bypass first
    if bypass:
        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Inspect bypass evidence for bad trace",
            when="bad trace has bypass attempt or ACK under verify FAIL",
            command=f"./prompt-dsl-system/tools/run.sh trace-open -r . --trace-id {bad_trace}",
            expected="risk/verify context displayed",
            stop_if="release_gate_bypass_attempt confirmed",
            risk="medium",
        )
        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Force verification before any further promotion",
            when="verify FAIL and bypass signal present",
            command="./prompt-dsl-system/tools/run.sh verify-followup-fixes -r . --moves <MOVES_JSON>",
            expected="verify report reaches PASS or WARN",
            stop_if="verify still FAIL",
            risk="low",
        )
        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Re-check release gate with loop protection",
            when="after verification rerun",
            command="./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE_PATH> --verify-gate true --fail-on-loop true",
            expected="no bypass warning, controlled gate outcome",
            stop_if="risk gate still requests ACK under FAIL",
            risk="medium",
        )

    # P1 verify failures
    if verify_fail or verify_changed:
        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Open bad trace chain and check verify/risk reports",
            when="verify status regresses or FAIL appears",
            command=f"./prompt-dsl-system/tools/run.sh trace-open -r . --trace-id {bad_trace}",
            expected="verify/risk report paths confirmed",
            stop_if="missing verify report path",
            risk="none",
        )
        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Run follow-up verification",
            when="verify_top is FAIL or FAIL count increased",
            command="./prompt-dsl-system/tools/run.sh verify-followup-fixes -r . --moves <MOVES_JSON>",
            expected="followup_verify_report updated",
            stop_if="status remains FAIL",
            risk="low",
        )
        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Generate follow-up patch plan (plan only)",
            when="verify report still has residual hits",
            command="./prompt-dsl-system/tools/run.sh apply-followup-fixes -r . --scan-report <SCAN_REPORT_JSON> --mode plan",
            expected="followup_patch_plan.json generated",
            stop_if="no safe high-confidence replacements",
            risk="low",
        )
        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Re-run verification after patch planning",
            when="patch plan generated",
            command="./prompt-dsl-system/tools/run.sh verify-followup-fixes -r . --moves <MOVES_JSON>",
            expected="status converges to PASS/WARN",
            stop_if="status remains FAIL",
            risk="low",
        )

    # P2 guard/boundary
    if guard_delta > 0:
        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Run guard precheck with explicit module boundary",
            when="guard/outside-module blocking increases",
            command="./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH> --generate-plans true --plans both --only-violations true",
            expected="guard_report + move/rollback plans refreshed",
            stop_if="guard decision remains fail",
            risk="low",
        )
        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Generate move remediation plan (no apply)",
            when="outside-module violations present",
            command="./prompt-dsl-system/tools/run.sh apply-move -r . -m <MODULE_PATH>",
            expected="move_plan + rollback_plan ready",
            stop_if="move plan unavailable",
            risk="low",
        )
        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Re-run pipeline in guarded mode",
            when="guard plans prepared",
            command="./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE_PATH>",
            expected="guard blocks removed or clearly narrowed",
            stop_if="blocked by guard_gate again",
            risk="medium",
        )

    # P3 loop issues
    if loop_delta > 0 or int((bad.get("blocked_by_counts") or {}).get("loop_gate", 0)) > 0:
        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Refresh health view for loop evidence",
            when="loop_gate increased",
            command="./prompt-dsl-system/tools/run.sh validate -r . --health-window 30",
            expected="health_report + health_runbook regenerated",
            stop_if="loop trigger persists as top signal",
            risk="none",
        )
        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Inspect runbook to reduce repetitive edits",
            when="after health report refresh",
            command="cat prompt-dsl-system/tools/health_runbook.md",
            expected="shortest stabilization path reviewed",
            stop_if="runbook suggests unresolved gate prerequisites",
            risk="none",
        )
        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Run pipeline with loop hard-stop",
            when="loop persists after diagnostics",
            command="./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE_PATH> --fail-on-loop true",
            expected="either stable pass or immediate loop block",
            stop_if="exit code=3 (loop blocked)",
            risk="medium",
        )

    # P4 snapshot/deliveries evidence
    if has_snapshot or has_deliveries:
        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Locate snapshot chain for bad trace",
            when="bad trace has snapshot or deliveries",
            command=f"./prompt-dsl-system/tools/run.sh snapshot-open --repo-root . --trace-id {bad_trace}",
            expected="snapshot path candidate identified",
            stop_if="no snapshot candidates",
            risk="none",
        )

        snapshot_paths = bad_paths.get("snapshot_paths") if isinstance(bad_paths.get("snapshot_paths"), list) else []
        snapshot_arg = snapshot_paths[0] if snapshot_paths else "<SNAPSHOT_PATH>"
        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Generate restore guide (no rollback execution)",
            when="snapshot path available",
            command=f"./prompt-dsl-system/tools/run.sh snapshot-restore-guide -r . --snapshot {snapshot_arg}",
            expected="restore_guide + restore scripts generated",
            stop_if="strict mismatch or snapshot invalid",
            risk="low",
        )

        add_step(
            steps,
            seen_commands,
            max_steps,
            purpose="Compare deliveries file-set changes",
            when="deliveries delta may explain regressions",
            command=f"./prompt-dsl-system/tools/run.sh trace-diff -r . --a {s0_good} --b {bad_trace} --scan-deliveries true",
            expected="deliveries added/removed list updated",
            stop_if="deliveries diff too large and truncated",
            risk="none",
        )

    # Ensure minimum path length (5) when possible.
    min_steps = min(max_steps, 5)
    fallback: List[Tuple[str, str, str, str, str, str]] = [
        (
            "Open bad trace quickly",
            "fallback",
            f"./prompt-dsl-system/tools/run.sh trace-open -r . --trace-id {bad_trace}",
            "trace chain shown",
            "trace missing",
            "none",
        ),
        (
            "Refresh trace index",
            "fallback",
            "./prompt-dsl-system/tools/run.sh trace-index -r .",
            "trace_index refreshed",
            "index generation fails",
            "none",
        ),
        (
            "Refresh validation baseline",
            "fallback",
            "./prompt-dsl-system/tools/run.sh validate -r .",
            "errors/warnings updated",
            "validate errors > 0",
            "none",
        ),
        (
            "Generate conservative guard preview",
            "fallback",
            "./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH>",
            "guard_report generated",
            "module path missing",
            "low",
        ),
        (
            "Generate evidence diff again",
            "fallback",
            f"./prompt-dsl-system/tools/run.sh trace-diff -r . --a {s0_good} --b {bad_trace} --scan-deliveries false",
            "diff remains reproducible",
            "diff command unresolved",
            "none",
        ),
    ]
    for purpose, when, cmd, expected, stop_if, risk in fallback:
        if len(steps) >= min_steps:
            break
        add_step(steps, seen_commands, max_steps, purpose, when, cmd, expected, stop_if, risk)

    return steps[:max_steps]


def build_signals(good: Optional[Dict[str, Any]], bad: Dict[str, Any]) -> Dict[str, Any]:
    good_blocked = good.get("blocked_by_counts", {}) if isinstance(good, dict) else {}
    bad_blocked = bad.get("blocked_by_counts", {})
    blocked_delta = diff_counts(good_blocked, bad_blocked)

    good_ack = good.get("ack_used_counts", {}) if isinstance(good, dict) else {}
    bad_ack = bad.get("ack_used_counts", {})

    ack_delta = diff_counts(good_ack, bad_ack)

    good_verify_top = good.get("verify_top") if isinstance(good, dict) else "MISSING"
    bad_verify_top = bad.get("verify_top", "MISSING")

    bypass = bool(bad.get("bypass_attempt", False)) or (
        str(bad_verify_top).upper() == "FAIL" and int(bad.get("ack_total", 0)) > 0
    )

    return {
        "verify_changed": str(good_verify_top) != str(bad_verify_top),
        "blocked_by_delta": blocked_delta,
        "ack_delta": ack_delta,
        "bypass_attempt": bypass,
    }


def build_plan(
    repo_root: Path,
    good: Optional[Dict[str, Any]],
    bad: Dict[str, Any],
    good_missing: bool,
    max_steps: int,
) -> Dict[str, Any]:
    signals = build_signals(good=good, bad=bad)
    steps = build_plan_steps(good=good, bad=bad, signals=signals, max_steps=max_steps)

    placeholders = list(PLACEHOLDERS_DEFAULT)
    if good_missing:
        placeholders.append("GOOD_TRACE_ID")
    if any("<SNAPSHOT_PATH>" in str(step.get("command") or "") for step in steps):
        placeholders.append("SNAPSHOT_PATH")

    # De-duplicate placeholders while preserving order.
    seen: set[str] = set()
    ordered_ph: List[str] = []
    for ph in placeholders:
        if ph in seen:
            continue
        seen.add(ph)
        ordered_ph.append(ph)

    good_obj = {
        "trace_id": good.get("trace_id") if isinstance(good, dict) else None,
        "last_seen_at": good.get("last_seen_at") if isinstance(good, dict) else None,
        "verify_top": good.get("verify_top") if isinstance(good, dict) else None,
        "latest_exit_code": good.get("latest_exit_code") if isinstance(good, dict) else None,
    }
    bad_obj = {
        "trace_id": bad.get("trace_id"),
        "last_seen_at": bad.get("last_seen_at"),
        "verify_top": bad.get("verify_top"),
        "latest_exit_code": bad.get("latest_exit_code"),
    }

    return {
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "good": good_obj,
        "bad": bad_obj,
        "good_missing": bool(good_missing),
        "signals": signals,
        "steps": steps,
        "placeholders": ordered_ph,
    }


def build_plan_md(plan: Dict[str, Any]) -> str:
    good = plan.get("good") if isinstance(plan.get("good"), dict) else {}
    bad = plan.get("bad") if isinstance(plan.get("bad"), dict) else {}
    signals = plan.get("signals") if isinstance(plan.get("signals"), dict) else {}
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    good_missing = bool(plan.get("good_missing", False))

    lines: List[str] = []
    lines.append("# Trace Bisect Plan")
    lines.append(
        f"- Good: {good.get('trace_id') or '<MISSING>'} (last_seen={good.get('last_seen_at')}, verify_top={good.get('verify_top')}, latest_exit={good.get('latest_exit_code')})"
    )
    lines.append(
        f"- Bad: {bad.get('trace_id')} (last_seen={bad.get('last_seen_at')}, verify_top={bad.get('verify_top')}, latest_exit={bad.get('latest_exit_code')})"
    )
    lines.append("- Why this plan:")
    lines.append(f"  - verify_changed={signals.get('verify_changed')}")
    lines.append(f"  - blocked_by_delta={signals.get('blocked_by_delta')}")
    lines.append(f"  - bypass_attempt={signals.get('bypass_attempt')}")
    if good_missing:
        lines.append("  - good trace not auto-resolved: provide --good or set GOOD_TRACE_ID placeholder")
    lines.append("")

    lines.append("## Fill-in Guide")
    lines.append("- <MODULE_PATH>: 例如 `src/main/java/com/indihx/ownercommittee`")
    lines.append("- <PIPELINE_PATH>: 例如 `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md`")
    lines.append("- <MOVES_JSON>: 例如 `prompt-dsl-system/tools/moves_mapping_rename_suffix.json`")
    lines.append("- <SCAN_REPORT_JSON>: 例如 `prompt-dsl-system/tools/followup_scan_report_rename_suffix.json`")
    if any("<SNAPSHOT_PATH>" in str(s.get("command") or "") for s in steps if isinstance(s, dict)):
        lines.append("- <SNAPSHOT_PATH>: 例如 `prompt-dsl-system/tools/snapshots/snapshot_...`")
    if good_missing:
        lines.append("- <GOOD_TRACE_ID>: 用 trace-index/trace-open 选一个最近 PASS 的 trace")
    lines.append("")

    lines.append("## Steps (Shortest)")
    for step in steps:
        if not isinstance(step, dict):
            continue
        lines.append(f"### {step.get('id')} {step.get('purpose')}")
        lines.append("```bash")
        lines.append(str(step.get("command") or ""))
        lines.append("```")
        lines.append(f"Expected: {step.get('expected')}")
        lines.append(f"Stop if: {step.get('stop_if')}")
        lines.append("")

    lines.append("If you must ACK")
    lines.append("- 建议追加 `--ack-note` 记录放行理由。")
    lines.append("- 先生成 `snapshot-restore-guide`，再考虑 ACK 推进。")
    return "\n".join(lines) + "\n"


def command_to_shell(command: str) -> str:
    rendered = command
    for ph in re.findall(r"<([A-Z_][A-Z0-9_]*)>", rendered):
        rendered = rendered.replace(f"<{ph}>", f"${{{ph}}}")
    return rendered


def build_plan_sh(plan: Dict[str, Any]) -> str:
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    placeholders = plan.get("placeholders") if isinstance(plan.get("placeholders"), list) else []

    ph_set = {str(x) for x in placeholders if isinstance(x, str)}

    lines: List[str] = []
    lines.append("#!/usr/bin/env bash")
    lines.append("set -euo pipefail")
    lines.append("")
    lines.append('REPO_ROOT="${REPO_ROOT:-.}"')
    lines.append('DRY_RUN="${DRY_RUN:-1}"')
    if "MODULE_PATH" in ph_set:
        lines.append('MODULE_PATH="${MODULE_PATH:-}"')
    if "PIPELINE_PATH" in ph_set:
        lines.append('PIPELINE_PATH="${PIPELINE_PATH:-}"')
    if "MOVES_JSON" in ph_set:
        lines.append('MOVES_JSON="${MOVES_JSON:-}"')
    if "SCAN_REPORT_JSON" in ph_set:
        lines.append('SCAN_REPORT_JSON="${SCAN_REPORT_JSON:-}"')
    if "SNAPSHOT_PATH" in ph_set:
        lines.append('SNAPSHOT_PATH="${SNAPSHOT_PATH:-}"')
    if "GOOD_TRACE_ID" in ph_set:
        lines.append('GOOD_TRACE_ID="${GOOD_TRACE_ID:-}"')
    lines.append("")
    lines.append("run_cmd() {")
    lines.append('  local cmd="$1"')
    lines.append('  if [ "${DRY_RUN}" = "1" ]; then')
    lines.append('    echo "[DRY_RUN] ${cmd}"')
    lines.append("  else")
    lines.append('    echo "[RUN] ${cmd}"')
    lines.append('    eval "${cmd}"')
    lines.append("  fi")
    lines.append("}")
    lines.append("")
    lines.append("require_var() {")
    lines.append('  local name="$1"')
    lines.append('  local val="${!name:-}"')
    lines.append('  if [ -z "${val}" ]; then')
    lines.append('    echo "[ERROR] Missing required variable: ${name}" >&2')
    lines.append('    exit 2')
    lines.append("  fi")
    lines.append("}")
    lines.append("")

    for step in steps:
        if not isinstance(step, dict):
            continue
        sid = str(step.get("id") or "")
        purpose = str(step.get("purpose") or "")
        requires = step.get("requires") if isinstance(step.get("requires"), list) else []
        command = command_to_shell(str(step.get("command") or ""))

        lines.append(f"echo '[{sid}] {purpose}'")
        for req in requires:
            if not isinstance(req, str):
                continue
            lines.append(f"require_var {req}")
        escaped = command.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'run_cmd "{escaped}"')
        lines.append("")

    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate trace bisect plan")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--policy", default="", help="Optional policy YAML path")
    parser.add_argument("--policy-override", action="append", default=[], help="Policy override key=value")
    parser.add_argument("--tools-dir", default="")
    parser.add_argument("--index", default="")
    parser.add_argument("--bad", required=True)
    parser.add_argument("--good", default="")
    parser.add_argument("--auto-find-good", default="")
    parser.add_argument("--verify-top", default="", choices=["PASS", "WARN", "FAIL", "MISSING", ""])
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--max-steps", default="")
    parser.add_argument("--emit-sh", default="true")
    parser.add_argument("--emit-md", default="true")
    args = parser.parse_args(argv)

    cwd = Path.cwd().resolve()
    repo_root = to_path(str(args.repo_root), cwd)

    policy_overrides = build_cli_override_dict(
        repo_root=repo_root,
        policy_path=str(getattr(args, "policy", "") or "").strip(),
        policy_override_exprs=getattr(args, "policy_override", []) or [],
    )
    policy = load_policy(repo_root, cli_overrides=policy_overrides)

    tools_dir_default = str(get_policy_value(policy, "paths.tools_dir", DEFAULT_TOOLS_DIR) or DEFAULT_TOOLS_DIR)
    index_default = str(get_policy_value(policy, "paths.trace_index_json", DEFAULT_INDEX_REL) or DEFAULT_INDEX_REL)
    auto_find_default = parse_cli_bool(get_policy_value(policy, "bisect.auto_find_good", True), default=True)
    verify_top_default = str(get_policy_value(policy, "bisect.good_verify_top", "PASS") or "PASS").upper()
    if verify_top_default not in {"PASS", "WARN", "FAIL", "MISSING"}:
        verify_top_default = "PASS"
    max_steps_default = parse_int(get_policy_value(policy, "bisect.max_steps", 12), default=12, minimum=5)

    tools_dir = to_path(str(args.tools_dir).strip() or tools_dir_default, repo_root)
    index_path = to_path(str(args.index), repo_root) if str(args.index).strip() else to_path(index_default, repo_root)
    output_dir = to_path(str(args.output_dir), repo_root) if str(args.output_dir).strip() else tools_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if not index_path.exists() or not index_path.is_file():
        ok = run_trace_indexer(repo_root=repo_root, tools_dir=tools_dir, output_dir=index_path.parent)
        if not ok:
            print("Failed to auto-generate trace index", file=sys.stderr)
            return 2
        if not index_path.exists() and index_path.name != "trace_index.json":
            fallback = (index_path.parent / "trace_index.json").resolve()
            if fallback.exists():
                index_path = fallback

    index_data = safe_read_json(index_path)
    items = index_data.get("items") if isinstance(index_data.get("items"), list) else []

    bad_item, bad_candidates = match_trace(items, str(args.bad), latest=True)
    if bad_item is None:
        print(f"Bad trace not found: {args.bad}", file=sys.stderr)
        if bad_candidates:
            for cand in bad_candidates[:10]:
                print(f"- {cand.get('trace_id')} | {cand.get('last_seen_at')}", file=sys.stderr)
        return 2

    bad_summary = summarize_trace(bad_item)

    good_summary: Optional[Dict[str, Any]] = None
    good_missing = False
    good_arg = str(args.good or "").strip()
    if good_arg:
        good_item, good_candidates = match_trace(items, good_arg, latest=True)
        if good_item is None:
            print(f"Good trace not found: {good_arg}", file=sys.stderr)
            if good_candidates:
                for cand in good_candidates[:10]:
                    print(f"- {cand.get('trace_id')} | {cand.get('last_seen_at')}", file=sys.stderr)
            return 2
        good_summary = summarize_trace(good_item)
    else:
        auto_find = parse_cli_bool(args.auto_find_good, default=auto_find_default)
        if auto_find:
            good_summary = choose_good_auto(
                items,
                bad=bad_summary,
                verify_top=(str(args.verify_top).strip().upper() or verify_top_default),
            )
        if good_summary is None:
            good_missing = True

    max_steps = parse_int(args.max_steps, default=max_steps_default, minimum=5)
    if max_steps > 12:
        max_steps = 12

    plan = build_plan(
        repo_root=repo_root,
        good=good_summary,
        bad=bad_summary,
        good_missing=good_missing,
        max_steps=max_steps,
    )

    out_json = (output_dir / "bisect_plan.json").resolve()
    out_md = (output_dir / "bisect_plan.md").resolve()
    out_sh = (output_dir / "bisect_plan.sh").resolve()

    out_json.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    emit_md = parse_cli_bool(args.emit_md, default=True)
    if emit_md:
        out_md.write_text(build_plan_md(plan), encoding="utf-8")

    emit_sh = parse_cli_bool(args.emit_sh, default=True)
    if emit_sh:
        out_sh.write_text(build_plan_sh(plan), encoding="utf-8")
        try:
            out_sh.chmod(0o755)
        except OSError:
            pass

    print(f"bisect_plan_json: {out_json}")
    if emit_md:
        print(f"bisect_plan_md: {out_md}")
    if emit_sh:
        print(f"bisect_plan_sh: {out_sh}")
    if good_missing:
        print("[WARN] good trace not auto-selected; provide --good or set GOOD_TRACE_ID", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
