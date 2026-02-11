#!/usr/bin/env python3
"""Detect anti-loop signals from trace history.

Standard-library only.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from policy_loader import build_cli_override_dict, get_policy_value, load_policy

PUSH_COMMANDS = {"run", "apply-move", "apply-followup-fixes"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_bool(value: Any, default: bool) -> bool:
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


def normalize_rel(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    s = str(text).strip().replace("\\", "/")
    if not s:
        return None
    while s.startswith("./"):
        s = s[2:]
    return s or None


def parse_int(value: Any, default: int, minimum: int = 1) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if n < minimum:
        return minimum
    return n


def load_jsonl(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    records: List[Dict[str, Any]] = []
    if not path.exists():
        return records, warnings

    lines = path.read_text(encoding="utf-8").splitlines()
    for idx, raw in enumerate(lines, start=1):
        text = raw.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            warnings.append(f"invalid JSON at line {idx}, skipped")
            continue
        if not isinstance(obj, dict):
            warnings.append(f"non-object JSON at line {idx}, skipped")
            continue
        obj["_line"] = idx
        records.append(obj)

    return records, warnings


def select_scope_records(
    records: Sequence[Dict[str, Any]],
    same_trace_only: bool,
    trace_id: Optional[str],
    pipeline_path: Optional[str],
    effective_module_path: Optional[str],
) -> List[Dict[str, Any]]:
    trace_norm = trace_id.strip() if isinstance(trace_id, str) else None
    pipe_norm = normalize_rel(pipeline_path)
    mod_norm = normalize_rel(effective_module_path)

    scoped: List[Dict[str, Any]] = []

    if same_trace_only and trace_norm:
        for rec in records:
            if str(rec.get("trace_id", "")).strip() == trace_norm:
                scoped.append(rec)
        return scoped

    for rec in records:
        rec_pipe = normalize_rel(rec.get("pipeline_path"))
        rec_mod = normalize_rel(rec.get("effective_module_path"))

        if pipe_norm is not None and rec_pipe != pipe_norm:
            continue
        if mod_norm is not None and rec_mod != mod_norm:
            continue
        if mod_norm is None and rec_mod is not None:
            continue
        scoped.append(rec)

    return scoped


def select_release_scope_records(
    records: Sequence[Dict[str, Any]],
    pipeline_path: Optional[str],
    effective_module_path: Optional[str],
) -> List[Dict[str, Any]]:
    pipe_norm = normalize_rel(pipeline_path)
    mod_norm = normalize_rel(effective_module_path)

    scoped: List[Dict[str, Any]] = []
    for rec in records:
        rec_pipe = normalize_rel(rec.get("pipeline_path"))
        rec_mod = normalize_rel(rec.get("effective_module_path"))

        if mod_norm is not None and rec_mod != mod_norm:
            continue
        if mod_norm is None and rec_mod is not None:
            continue

        if pipe_norm is not None:
            # For release bypass detection, include same pipeline and push records without pipeline_path.
            if rec_pipe is not None and rec_pipe != pipe_norm:
                continue
        scoped.append(rec)

    return scoped


def changed_set(rec: Dict[str, Any]) -> set:
    sample = rec.get("changed_files_sample")
    if not isinstance(sample, list):
        return set()
    values = {str(x).strip() for x in sample if str(x).strip()}
    return values


def jaccard(a: set, b: set) -> float:
    union = a | b
    if not union:
        return 1.0
    inter = a & b
    return float(len(inter)) / float(len(union))


def rec_int(rec: Dict[str, Any], key: str) -> int:
    return parse_int(rec.get(key), 0, minimum=0)


def detect_rule_a(recent: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if len(recent) < 3:
        return None

    sims: List[float] = []
    comparable = 0
    for prev, curr in zip(recent[:-1], recent[1:]):
        a = changed_set(prev)
        b = changed_set(curr)
        if a or b:
            comparable += 1
        sims.append(jaccard(a, b))

    if comparable < 2:
        return None

    high_similarity = all(x >= 0.7 for x in sims)
    fail_count = sum(1 for rec in recent if str(rec.get("guard_decision", "")).lower() == "fail")
    violations = [rec_int(rec, "violations_count") for rec in recent]
    non_decreasing = all(curr >= prev for prev, curr in zip(violations[:-1], violations[1:]))

    if high_similarity and (fail_count >= 2 or non_decreasing):
        return {
            "id": "A_file_set_loop",
            "severity": "HIGH",
            "message": "Changed file sets are highly similar (Jaccard >= 0.7) while failures repeat or violations do not decline.",
            "details": {
                "jaccard_sequence": [round(x, 3) for x in sims],
                "fail_count": fail_count,
                "violations": violations,
            },
        }

    return None


def detect_rule_b(recent: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not recent:
        return None
    hit = sum(1 for rec in recent if rec_int(rec, "violations_count") >= 1)
    if hit >= 3:
        return {
            "id": "B_boundary_probing",
            "severity": "MEDIUM",
            "message": "Violations appeared repeatedly (>=3) in recent runs, indicating possible boundary probing.",
            "details": {"violation_runs": hit, "window": len(recent)},
        }
    return None


def detect_rule_c(recent: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if len(recent) < 3:
        return None
    last3 = list(recent[-3:])
    counts = [rec_int(rec, "changed_files_count") for rec in last3]
    monotonic_up = counts[0] < counts[1] < counts[2]
    growth = float(counts[2] - counts[0]) / float(max(counts[0], 1))
    if monotonic_up and growth >= 0.5:
        return {
            "id": "C_scope_expansion",
            "severity": "MEDIUM",
            "message": "Changed-file scope is expanding across recent runs (>=50% growth).",
            "details": {"counts": counts, "growth": round(growth, 3)},
        }
    return None


def detect_rule_d(effective_module_path: Optional[str]) -> Optional[Dict[str, Any]]:
    if normalize_rel(effective_module_path) is None:
        return {
            "id": "D_missing_module_path",
            "severity": "MEDIUM",
            "message": "Run executed without effective module_path; this increases blind-scan risk.",
            "details": {},
        }
    return None


def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    text = str(v).strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def detect_rule_e(recent: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if len(recent) < 2:
        return None

    attempts: List[Dict[str, Any]] = []
    for rec in recent:
        command = str(rec.get("command", "")).strip()
        verify_status = str(rec.get("verify_status", "")).strip().upper()
        verify_gate_required = _bool(rec.get("verify_gate_required", False))
        blocked_by = str(rec.get("blocked_by", "none")).strip()
        ack_used = str(rec.get("ack_used", "none")).strip()

        if command not in PUSH_COMMANDS:
            continue
        if verify_status != "FAIL":
            continue
        if not verify_gate_required:
            continue

        bypass = (blocked_by != "verify_gate") or (ack_used != "none")
        if not bypass:
            continue

        raw_hits = rec.get("verify_hits_total")
        verify_hits_total = None
        if isinstance(raw_hits, int):
            verify_hits_total = max(raw_hits, 0)
        elif isinstance(raw_hits, float):
            verify_hits_total = max(int(raw_hits), 0)

        attempts.append(
            {
                "line": rec.get("_line"),
                "timestamp": rec.get("timestamp"),
                "command": command,
                "verify_hits_total": verify_hits_total,
                "ack_used": ack_used,
                "blocked_by": blocked_by,
                "action": rec.get("action"),
            }
        )

    if len(attempts) < 2:
        return None

    return {
        "id": "release_gate_bypass_attempt",
        "severity": "HIGH",
        "message": "Repeated attempts to push commands while verify status is FAIL and verify gate is bypassed/acked.",
        "details": {
            "attempt_count": len(attempts),
            "recent_attempts": attempts[-6:],
        },
    }


def build_evidence(recent: Sequence[Dict[str, Any]], recent_attempts: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if not recent:
        return {
            "line_range": None,
            "time_range": None,
            "records": [],
        }

    lines = [int(rec.get("_line", 0)) for rec in recent if int(rec.get("_line", 0)) > 0]
    line_range = None
    if lines:
        line_range = f"{min(lines)}-{max(lines)}"

    ts_values = [str(rec.get("timestamp", "")).strip() for rec in recent if str(rec.get("timestamp", "")).strip()]
    time_range = None
    if ts_values:
        time_range = f"{ts_values[0]} ~ {ts_values[-1]}"

    rows: List[Dict[str, Any]] = []
    for rec in recent:
        rows.append(
            {
                "line": rec.get("_line"),
                "timestamp": rec.get("timestamp"),
                "action": rec.get("action"),
                "guard_decision": rec.get("guard_decision"),
                "violations_count": rec_int(rec, "violations_count"),
                "changed_files_count": rec_int(rec, "changed_files_count"),
                "pipeline_path": rec.get("pipeline_path"),
                "effective_module_path": rec.get("effective_module_path"),
            }
        )

    return {
        "line_range": line_range,
        "time_range": time_range,
        "records": rows,
        "recent_attempts": recent_attempts or [],
    }


def decide_level(triggers: Sequence[Dict[str, Any]]) -> str:
    if any(str(t.get("severity", "")).upper() == "HIGH" for t in triggers):
        return "HIGH"
    if any(str(t.get("severity", "")).upper() == "MEDIUM" for t in triggers):
        return "MEDIUM"
    if any(str(t.get("severity", "")).upper() == "LOW" for t in triggers):
        return "LOW"
    return "NONE"


def build_recommendation(level: str, triggers: Sequence[Dict[str, Any]]) -> List[str]:
    trigger_ids = {str(t.get("id", "")).strip() for t in triggers if isinstance(t, dict)}
    if "release_gate_bypass_attempt" in trigger_ids:
        return [
            "First fix verify FAIL: run verify-followup-fixes until status is PASS.",
            "Do not continue push commands now; keep verify-gate=true and enable --fail-on-loop.",
            "If promotion is unavoidable, provide manual ACK with an explicit reason note (--ack-note).",
        ]
    if level == "HIGH":
        return [
            "Run debug-guard and inspect guard_report.json + loop_diagnostics.md first.",
            "Apply scope fixes with apply-move (explicit confirmation): ./prompt-dsl-system/tools/run.sh apply-move -r . -m <MODULE_PATH> --yes --move-dry-run false",
            "If still unstable, request user intervention and execute rollback plan.",
        ]
    if level == "MEDIUM":
        return [
            "Review loop_diagnostics.md evidence and confirm module boundary (-m).",
            "Run debug-guard, then prioritize move plan for out-of-scope changes.",
            "If violations persist, use rollback plan and reduce scope.",
        ]
    return ["No anti-loop risk detected. Continue with validate/run."]


def write_markdown(path: Path, level: str, triggers: Sequence[Dict[str, Any]], evidence: Dict[str, Any], recommendation: Sequence[str]) -> None:
    lines: List[str] = []
    lines.append("# loop_diagnostics")
    lines.append("")
    lines.append(f"- generated_at: {now_iso()}")
    lines.append(f"- level: {level}")
    lines.append("")
    lines.append("## 现象")
    if not triggers:
        lines.append("- 未检测到显著 loop 信号。")
    else:
        for item in triggers:
            lines.append(
                f"- [{str(item.get('severity', 'UNKNOWN')).upper()}] {item.get('id', 'unknown')}: {item.get('message', '')}"
            )

    lines.append("")
    lines.append("## 证据")
    lines.append(f"- line_range: {evidence.get('line_range')}")
    lines.append(f"- time_range: {evidence.get('time_range')}")
    lines.append("")
    lines.append("| line | timestamp | action | guard | violations | changed |")
    lines.append("|---|---|---|---|---:|---:|")
    rows = evidence.get("records", [])
    if not isinstance(rows, list) or not rows:
        lines.append("| - | - | - | - | - | - |")
    else:
        for row in rows[-6:]:
            lines.append(
                f"| {row.get('line','-')} | {row.get('timestamp','-')} | {row.get('action','-')} | {row.get('guard_decision','-')} | {row.get('violations_count','-')} | {row.get('changed_files_count','-')} |"
            )

    lines.append("")
    lines.append("## 建议")
    for idx, rec in enumerate(list(recommendation)[:3], start=1):
        lines.append(f"{idx}. {rec}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Anti-loop detector for pipeline runner traces")
    p.add_argument("--repo-root", default=".", help="Repository root path")
    p.add_argument("--policy", default="", help="Optional policy YAML path")
    p.add_argument("--policy-override", action="append", default=[], help="Policy override key=value")
    p.add_argument(
        "--history",
        default="",
        help="Trace history jsonl path",
    )
    p.add_argument("--context-id", help="Current context_id")
    p.add_argument("--trace-id", help="Current trace_id")
    p.add_argument("--pipeline-path", help="Current pipeline path")
    p.add_argument("--effective-module-path", help="Current effective module path")
    p.add_argument("--window", default="", help="History window size")
    p.add_argument("--same-trace-only", default="true", help="true/false, default true")
    p.add_argument(
        "--output-dir",
        default="prompt-dsl-system/tools",
        help="Output directory for loop_diagnostics.{json,md}",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        print(f"Invalid repo root: {repo_root}")
        return 2

    policy_overrides = build_cli_override_dict(
        repo_root=repo_root,
        policy_path=str(getattr(args, "policy", "") or "").strip(),
        policy_override_exprs=getattr(args, "policy_override", []) or [],
    )
    policy = load_policy(repo_root, cli_overrides=policy_overrides)

    history_default = str(
        get_policy_value(policy, "paths.trace_history", "prompt-dsl-system/tools/trace_history.jsonl")
        or "prompt-dsl-system/tools/trace_history.jsonl"
    )
    output_default = str(get_policy_value(policy, "paths.tools_dir", "prompt-dsl-system/tools") or "prompt-dsl-system/tools")
    window_default = parse_int(get_policy_value(policy, "gates.loop_gate.window", 6), default=6, minimum=2)

    history_path = Path(str(args.history or "").strip() or history_default)
    if not history_path.is_absolute():
        history_path = (repo_root / history_path).resolve()

    output_dir = Path(str(args.output_dir or "").strip() or output_default)
    if not output_dir.is_absolute():
        output_dir = (repo_root / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    window = parse_int(args.window, default=window_default, minimum=2)
    same_trace_only = parse_bool(args.same_trace_only, default=True)

    records, warnings = load_jsonl(history_path)

    scoped = select_scope_records(
        records=records,
        same_trace_only=same_trace_only,
        trace_id=args.trace_id,
        pipeline_path=args.pipeline_path,
        effective_module_path=args.effective_module_path,
    )
    recent = scoped[-window:] if window > 0 else list(scoped)
    # Rule E always uses pipeline/module scope and has highest priority.
    release_scope = select_release_scope_records(
        records=records,
        pipeline_path=args.pipeline_path,
        effective_module_path=args.effective_module_path,
    )
    recent_release_scope = release_scope[-window:] if window > 0 else list(release_scope)

    triggers: List[Dict[str, Any]] = []
    rule_e = detect_rule_e(recent_release_scope)
    if rule_e:
        triggers.append(rule_e)

    rule_a = detect_rule_a(recent)
    if rule_a:
        triggers.append(rule_a)
    rule_b = detect_rule_b(recent)
    if rule_b:
        triggers.append(rule_b)
    rule_c = detect_rule_c(recent)
    if rule_c:
        triggers.append(rule_c)
    rule_d = detect_rule_d(args.effective_module_path)
    if rule_d:
        triggers.append(rule_d)

    level = decide_level(triggers)
    recent_attempts: List[Dict[str, Any]] = []
    if rule_e and isinstance(rule_e.get("details"), dict):
        raw_attempts = rule_e["details"].get("recent_attempts")
        if isinstance(raw_attempts, list):
            recent_attempts = raw_attempts
    evidence = build_evidence(recent, recent_attempts=recent_attempts)
    recommendation = build_recommendation(level, triggers)

    diagnostics = {
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "history_path": str(history_path),
        "window": window,
        "same_trace_only": same_trace_only,
        "level": level,
        "triggers": triggers,
        "warnings": warnings,
        "evidence": evidence,
        "recommendation": recommendation,
        "history_size": len(records),
        "considered_size": len(scoped),
        "release_scope_size": len(release_scope),
        "recent_size": len(recent),
        "context_id": args.context_id,
        "trace_id": args.trace_id,
        "pipeline_path": normalize_rel(args.pipeline_path),
        "effective_module_path": normalize_rel(args.effective_module_path),
    }

    json_path = output_dir / "loop_diagnostics.json"
    md_path = output_dir / "loop_diagnostics.md"
    json_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(md_path, level, triggers, evidence, recommendation)

    print(f"[loop] level={level} recent={len(recent)} report={json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
