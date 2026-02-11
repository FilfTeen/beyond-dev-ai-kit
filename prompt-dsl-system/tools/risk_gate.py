#!/usr/bin/env python3
"""Risk gate with one-time ACK token.

Standard-library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from policy_loader import build_cli_override_dict, get_policy_value, load_policy

RANK = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
VERIFY_RANK = {"PASS": 0, "WARN": 1, "FAIL": 2}


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(text: str) -> Optional[datetime]:
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_int(value: Any, default: int, minimum: int = 0) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if n < minimum:
        return minimum
    return n


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


def risk_norm(level: Any) -> str:
    text = str(level or "NONE").strip().upper()
    return text if text in RANK else "NONE"


def max_risk(*levels: str) -> str:
    best = "NONE"
    for lv in levels:
        n = risk_norm(lv)
        if RANK[n] > RANK[best]:
            best = n
    return best


def verify_norm(status: Any) -> str:
    text = str(status or "MISSING").strip().upper()
    return text if text in {"PASS", "WARN", "FAIL"} else "MISSING"


def to_repo_path(repo_root: Path, path_arg: str) -> Path:
    p = Path(path_arg)
    if not p.is_absolute():
        p = (repo_root / p).resolve()
    else:
        p = p.resolve()
    return p


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def scrub_for_digest(value: Any) -> Any:
    volatile_keys = {
        "generated_at",
        "token_out",
        "token_json_out",
        "json_out",
        "next_cmd",
        "next_cmd_ack_file",
        "next_cmd_example",
    }
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key in sorted(value.keys()):
            if key in volatile_keys:
                continue
            out[key] = scrub_for_digest(value[key])
        return out
    if isinstance(value, list):
        return [scrub_for_digest(x) for x in value]
    return value


def json_digest(data: Dict[str, Any]) -> str:
    if not isinstance(data, dict) or not data:
        return ""
    raw = json.dumps(scrub_for_digest(data), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def classify_violation_type(v: Dict[str, Any]) -> str:
    t = str(v.get("type", "")).strip().lower()
    if t:
        return t
    rule = str(v.get("rule", "")).strip()
    if rule == "forbidden_path_patterns":
        return "forbidden"
    if rule == "module_path_required":
        return "missing_module_path"
    return "outside_module"


def build_guard_risk(guard: Dict[str, Any]) -> Tuple[str, List[str], Dict[str, Any]]:
    decision = str(guard.get("decision", "unknown")).strip().lower()
    violations_raw = guard.get("violations")
    violations = violations_raw if isinstance(violations_raw, list) else []
    violations_count = len(violations)

    types: List[str] = []
    for item in violations:
        if isinstance(item, dict):
            types.append(classify_violation_type(item))
    types_uniq = sorted(set(types))

    level = "NONE"
    reasons: List[str] = []

    if decision == "fail" and violations_count > 0:
        level = max_risk(level, "MEDIUM")
        reason = guard.get("decision_reason")
        if isinstance(reason, str) and reason.strip():
            reasons.append(f"guard fail: {reason.strip()}")
        else:
            reasons.append("guard fail with violations")

    if any(t in {"forbidden", "missing_module_path"} for t in types_uniq):
        level = "HIGH"
        reasons.append("guard violation includes forbidden or missing_module_path")

    evidence = {
        "guard_decision": guard.get("decision"),
        "guard_decision_reason": guard.get("decision_reason"),
        "violations_count": violations_count,
        "violation_types": types_uniq,
    }
    return level, reasons, evidence


def build_loop_risk(loop: Dict[str, Any]) -> Tuple[str, List[str], Dict[str, Any]]:
    level = risk_norm(loop.get("level", "NONE"))
    triggers_raw = loop.get("triggers")
    triggers = triggers_raw if isinstance(triggers_raw, list) else []

    trigger_ids: List[str] = []
    for item in triggers:
        if isinstance(item, dict):
            trigger_ids.append(str(item.get("id", "unknown")))
        else:
            trigger_ids.append(str(item))
    bypass_attempt_detected = "release_gate_bypass_attempt" in trigger_ids
    if bypass_attempt_detected:
        level = "HIGH"

    reasons: List[str] = []
    if level != "NONE":
        if trigger_ids:
            reasons.append(f"loop level={level}: triggers={', '.join(trigger_ids)}")
        else:
            reasons.append(f"loop level={level}")
    if bypass_attempt_detected:
        reasons.append("loop trigger release_gate_bypass_attempt detected")

    evidence = {
        "loop_level": level,
        "loop_triggers": trigger_ids,
        "loop_bypass_attempt_detected": bypass_attempt_detected,
    }
    return level, reasons, evidence


def build_verify_gate(
    verify_report: Dict[str, Any],
    verify_threshold: str,
    verify_as_risk: bool,
    verify_required_for: Sequence[str],
    command_name: str,
) -> Tuple[bool, str, Optional[int], List[str], Dict[str, Any], bool]:
    reasons: List[str] = []
    status = "MISSING"
    hits_total: Optional[int] = None
    gate_required = False
    gate_reason: Optional[str] = None
    applies_to_command = True

    required_set = {str(x).strip() for x in verify_required_for if str(x).strip()}
    cmd = str(command_name).strip()
    if required_set and cmd and cmd not in required_set:
        applies_to_command = False

    if isinstance(verify_report, dict) and verify_report:
        summary = verify_report.get("summary")
        if isinstance(summary, dict):
            status = verify_norm(summary.get("status"))
            raw_hits = summary.get("hits_total")
            if isinstance(raw_hits, int):
                hits_total = max(raw_hits, 0)
            elif isinstance(raw_hits, float):
                hits_total = max(int(raw_hits), 0)
    else:
        status = "MISSING"

    threshold = str(verify_threshold).strip().upper()
    if threshold not in VERIFY_RANK:
        threshold = "FAIL"

    if status == "MISSING":
        gate_required = False
        gate_reason = "verify report missing; run verify-followup-fixes before promote/apply commands."
    elif applies_to_command and VERIFY_RANK[status] >= VERIFY_RANK[threshold]:
        gate_required = True
        if hits_total is None:
            gate_reason = f"verify gate: {status}"
        else:
            gate_reason = f"verify gate: {status} (hits={hits_total})"
        reasons.append(gate_reason)

    evidence = {
        "verify_status": status,
        "verify_hits_total": hits_total,
        "verify_threshold": threshold,
        "verify_gate_required": gate_required,
        "verify_required_for": sorted(required_set),
        "verify_command_name": cmd,
        "verify_applies_to_command": applies_to_command,
        "verify_as_risk": bool(verify_as_risk),
    }
    return gate_required, gate_reason or "", hits_total, reasons, evidence, applies_to_command


def build_reason_hash(
    guard_evidence: Dict[str, Any],
    loop_evidence: Dict[str, Any],
    extra_evidence: Optional[Dict[str, Any]] = None,
) -> str:
    payload = {
        "guard": {
            "decision": guard_evidence.get("guard_decision"),
            "decision_reason": guard_evidence.get("guard_decision_reason"),
            "violations_count": guard_evidence.get("violations_count"),
            "violation_types": guard_evidence.get("violation_types"),
        },
        "loop": {
            "loop_level": loop_evidence.get("loop_level"),
            "loop_triggers": loop_evidence.get("loop_triggers"),
        },
    }
    if isinstance(extra_evidence, dict) and extra_evidence:
        payload["extra"] = extra_evidence
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_guard_violation_types(guard_evidence: Dict[str, Any]) -> List[str]:
    raw = guard_evidence.get("violation_types")
    if not isinstance(raw, list):
        return []
    types: List[str] = []
    for item in raw:
        text = str(item).strip().lower()
        if text in {"forbidden", "outside_module", "missing_module_path"}:
            types.append(text)
    return sorted(set(types))


def load_move_report_info(move_report: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(move_report, dict) or not move_report:
        return {
            "exists": False,
            "generated": False,
            "generated_reason": "move report missing",
            "summary_total": 0,
            "summary_movable": 0,
            "summary_non_movable": 0,
            "summary_high_risk": 0,
            "blockers": ["move report missing"],
            "movable_ratio": None,
        }

    generated = bool(move_report.get("generated", False))
    generated_reason = str(move_report.get("generated_reason", "")).strip() or (
        "ok" if generated else "move report not generated"
    )
    summary_raw = move_report.get("summary")
    summary = summary_raw if isinstance(summary_raw, dict) else {}
    total = parse_int(summary.get("total"), default=0, minimum=0)
    movable = parse_int(summary.get("movable"), default=0, minimum=0)
    non_movable = parse_int(summary.get("non_movable"), default=max(total - movable, 0), minimum=0)
    high_risk = parse_int(summary.get("high_risk"), default=0, minimum=0)

    blockers: List[str] = []
    blockers_raw = move_report.get("blockers")
    if isinstance(blockers_raw, list):
        for item in blockers_raw:
            text = str(item).strip()
            if text:
                blockers.append(text)

    items_raw = move_report.get("items")
    items = items_raw if isinstance(items_raw, list) else []
    if non_movable > 0:
        deny_reasons = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            if bool(item.get("can_move", False)):
                continue
            reason = str(item.get("deny_reason", "")).strip()
            if reason:
                deny_reasons.add(reason)
            risk_flags_raw = item.get("risk_flags")
            if isinstance(risk_flags_raw, list):
                for flag in risk_flags_raw:
                    text = str(flag).strip()
                    if text in {"dst_exists", "dst_exists_possible"}:
                        blockers.append("dst exists")
                    elif text in {"path_token_truncated", "dst_outside_module", "no_module_path"}:
                        blockers.append(text.replace("_", " "))
        blockers.extend(sorted(deny_reasons))

    movable_ratio = None
    if total > 0:
        movable_ratio = float(movable) / float(total)

    return {
        "exists": True,
        "generated": generated,
        "generated_reason": generated_reason,
        "summary_total": total,
        "summary_movable": movable,
        "summary_non_movable": non_movable,
        "summary_high_risk": high_risk,
        "blockers": sorted({b for b in blockers if b}),
        "movable_ratio": movable_ratio,
    }


def decide_auto_ack(
    overall_risk: str,
    guard_violation_types: Sequence[str],
    move_info: Dict[str, Any],
) -> Tuple[bool, Optional[str], List[str]]:
    types = {str(x).strip().lower() for x in guard_violation_types}
    blockers = [str(x) for x in move_info.get("blockers", []) if str(x).strip()]

    if "forbidden" in types:
        return False, "forbidden violations require manual acknowledgment", sorted(set(blockers + ["forbidden violations"]))

    if overall_risk != "HIGH":
        return True, None, sorted(set(blockers))

    if "missing_module_path" in types:
        return False, "missing module_path requires manual intervention", sorted(set(blockers + ["missing module_path"]))

    if "outside_module" in types:
        if not bool(move_info.get("generated", False)):
            reason = "outside_module but move plan unavailable"
            extra = str(move_info.get("generated_reason", "")).strip()
            if extra:
                blockers.append(extra)
            return False, reason, sorted(set(blockers + ["move plan unavailable"]))

        total = parse_int(move_info.get("summary_total"), default=0, minimum=0)
        non_movable = parse_int(move_info.get("summary_non_movable"), default=0, minimum=0)
        high_risk = parse_int(move_info.get("summary_high_risk"), default=0, minimum=0)

        if total <= 0:
            return False, "no move candidates but outside_module present", sorted(set(blockers + ["no move candidates"]))
        if non_movable > 0:
            return False, "some violations are not safely movable", sorted(set(blockers + ["non movable items"]))
        if high_risk > 0:
            return False, "move plan has high-risk conflicts (e.g., dst exists)", sorted(set(blockers + ["high risk move conflicts"]))
        return True, None, sorted(set(blockers))

    # HIGH risk from loop (without forbidden/outside/missing-module) is allowed for one-shot auto retry.
    return True, None, sorted(set(blockers))


def build_next_cmd_example(token: str) -> str:
    return (
        "./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> "
        "--pipeline <PIPELINE> --ack "
        f"{token}"
    )


def build_next_cmd_ack_latest() -> str:
    return "./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE> --ack-latest"


def build_next_cmd_ack_file(token_json_rel_path: str) -> str:
    return (
        "./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> "
        "--pipeline <PIPELINE> --ack-file "
        f"{token_json_rel_path}"
    )


def issue_token(
    repo_root: Path,
    overall_risk: str,
    reasons: Sequence[str],
    reason_hash: str,
    token_out: Path,
    token_json_out: Path,
    json_out: Path,
    ttl_minutes: int,
    threshold: str,
    exit_code: int,
) -> Dict[str, Any]:
    token = secrets.token_hex(16)
    issued_at = now_utc()
    expires_at = issued_at + timedelta(minutes=max(ttl_minutes, 0))

    reasons_limited = [str(x) for x in reasons[:5]]
    if not reasons_limited:
        reasons_limited = ["high risk context requires explicit acknowledgment"]

    token_out.parent.mkdir(parents=True, exist_ok=True)
    token_json_out.parent.mkdir(parents=True, exist_ok=True)
    token_json_rel = to_repo_relative(token_json_out, repo_root)
    next_cmd = build_next_cmd_ack_latest()
    next_cmd_ack_file = build_next_cmd_ack_file(token_json_rel)

    token_lines: List[str] = []
    token_lines.append(f"TOKEN: {token}")
    token_lines.append(f"RISK: {overall_risk}")
    token_lines.append(f"THRESHOLD: {threshold}")
    token_lines.append(f"ISSUED_AT: {iso(issued_at)}")
    token_lines.append(f"EXPIRES_AT: {iso(expires_at)}")
    token_lines.append("REASONS:")
    for idx, reason in enumerate(reasons_limited, start=1):
        token_lines.append(f"  {idx}. {reason}")
    token_lines.append(f"NEXT_CMD: {next_cmd}")
    token_lines.append(f"NEXT_CMD_ACK_FILE: {next_cmd_ack_file}")
    token_lines.append(f"NEXT_CMD_EXAMPLE: {build_next_cmd_example(token)}")
    token_out.write_text("\n".join(token_lines) + "\n", encoding="utf-8")

    token_record = {
        "token": token,
        "repo_root": str(repo_root),
        "overall_risk": overall_risk,
        "threshold": threshold,
        "reason_hash": reason_hash,
        "issued_at": iso(issued_at),
        "expires_at": iso(expires_at),
        "consumed": False,
        "consumed_at": None,
        "next_cmd": next_cmd,
        "next_cmd_ack_file": next_cmd_ack_file,
    }
    token_json_out.write_text(json.dumps(token_record, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "generated_at": iso(now_utc()),
        "repo_root": str(repo_root),
        "threshold": threshold,
        "overall_risk": overall_risk,
        "blocked": True,
        "acked": False,
        "ack_valid": False,
        "reason_hash": reason_hash,
        "reasons": list(reasons),
        "token_out": str(token_out),
        "token_json_out": str(token_json_out),
        "json_out": str(json_out),
        "next_cmd": next_cmd,
        "next_cmd_ack_file": next_cmd_ack_file,
        "next_cmd_example": build_next_cmd_example("<TOKEN>"),
        "token": {
            "value": token,
            "repo_root": str(repo_root),
            "overall_risk": overall_risk,
            "reason_hash": reason_hash,
            "issued_at": iso(issued_at),
            "expires_at": iso(expires_at),
            "consumed": False,
            "consumed_at": None,
        },
        "exit_code": exit_code,
    }
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def validate_ack(
    ack: str,
    repo_root: Path,
    overall_risk: str,
    reason_hash: str,
    token_json_out: Path,
    json_out: Path,
    consume_on_pass: bool,
) -> Tuple[bool, str, Dict[str, Any]]:
    token_data = safe_read_json(token_json_out)
    token_value = ""
    if isinstance(token_data.get("token"), str):
        token_value = str(token_data.get("token", ""))

    if not token_value:
        prev = safe_read_json(json_out)
        token_obj = prev.get("token")
        if isinstance(token_obj, dict):
            token_value = str(token_obj.get("value", ""))
            if token_value:
                token_data = {
                    "token": token_value,
                    "repo_root": token_obj.get("repo_root"),
                    "overall_risk": token_obj.get("overall_risk"),
                    "reason_hash": token_obj.get("reason_hash"),
                    "issued_at": token_obj.get("issued_at"),
                    "expires_at": token_obj.get("expires_at"),
                    "consumed": token_obj.get("consumed", False),
                    "consumed_at": token_obj.get("consumed_at"),
                }
    if not token_value:
        return False, "no issued token found", {}

    if ack.strip() != token_value:
        return False, "ack token mismatch", token_data

    if bool(token_data.get("consumed", False)):
        return False, "ack token already consumed", token_data

    token_repo = str(token_data.get("repo_root", ""))
    if token_repo != str(repo_root):
        return False, "ack token repo_root mismatch", token_data

    token_risk = risk_norm(token_data.get("overall_risk", "NONE"))
    if token_risk != overall_risk:
        return False, "ack token risk level mismatch", token_data

    token_hash = str(token_data.get("reason_hash", ""))
    if token_hash != reason_hash:
        return False, "ack token reason hash mismatch", token_data

    expires = parse_iso(str(token_data.get("expires_at", "")))
    if expires is None:
        return False, "ack token expiry parse failed", token_data
    if now_utc() > expires:
        return False, "ack token expired", token_data

    if consume_on_pass:
        token_data["consumed"] = True
        token_data["consumed_at"] = iso(now_utc())
        token_json_out.parent.mkdir(parents=True, exist_ok=True)
        token_json_out.write_text(
            json.dumps(token_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        prev = safe_read_json(json_out)
        token_obj = prev.get("token") if isinstance(prev.get("token"), dict) else {}
        token_obj["value"] = token_value
        token_obj["repo_root"] = token_data.get("repo_root")
        token_obj["overall_risk"] = token_data.get("overall_risk")
        token_obj["reason_hash"] = token_data.get("reason_hash")
        token_obj["issued_at"] = token_data.get("issued_at")
        token_obj["expires_at"] = token_data.get("expires_at")
        token_obj["consumed"] = token_data.get("consumed", False)
        token_obj["consumed_at"] = token_data.get("consumed_at")
        prev["token"] = token_obj
        prev["acked"] = True
        prev["ack_valid"] = True
        prev["blocked"] = False
        prev["generated_at"] = iso(now_utc())
        prev["overall_risk"] = overall_risk
        prev["reason_hash"] = reason_hash
        json_out.write_text(json.dumps(prev, ensure_ascii=False, indent=2), encoding="utf-8")
        return True, "ack accepted", token_data

    return True, "ack accepted", token_data


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Risk gate requiring one-time ACK token for high risk")
    p.add_argument("--repo-root", required=True, help="Repository root")
    p.add_argument("--policy", default="", help="Optional policy YAML path")
    p.add_argument("--policy-override", action="append", default=[], help="Policy override key=value")
    p.add_argument("--guard-report", default="prompt-dsl-system/tools/guard_report.json")
    p.add_argument("--loop-report", default="prompt-dsl-system/tools/loop_diagnostics.json")
    p.add_argument("--move-report", default="prompt-dsl-system/tools/move_report.json")
    p.add_argument("--verify-report", default="prompt-dsl-system/tools/followup_verify_report.json")
    p.add_argument("--verify-threshold", default="", choices=["PASS", "WARN", "FAIL", ""])
    p.add_argument(
        "--verify-as-risk",
        default="true",
        help="true/false; when true verify threshold breach elevates overall risk to HIGH",
    )
    p.add_argument(
        "--verify-required-for",
        action="append",
        default=[],
        help="Optional command names for which verify gate is enforced (repeatable).",
    )
    p.add_argument(
        "--command-name",
        default="",
        help="Current command name, used with --verify-required-for filtering.",
    )
    p.add_argument("--scan-report", default="")
    p.add_argument("--patch-plan", default="")
    p.add_argument("--threshold", default="", choices=["LOW", "MEDIUM", "HIGH", ""])
    p.add_argument("--ack", help="ACK token")
    p.add_argument("--token-out", default="prompt-dsl-system/tools/RISK_GATE_TOKEN.txt")
    p.add_argument("--token-json-out", default="prompt-dsl-system/tools/RISK_GATE_TOKEN.json")
    p.add_argument("--json-out", default="prompt-dsl-system/tools/risk_gate_report.json")
    p.add_argument("--mode", default="check", choices=["check", "issue"])
    p.add_argument("--ttl-minutes", default="")
    p.add_argument("--exit-code", default="")
    p.add_argument("--consume-on-pass", default="true", help="true/false, default true")
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

    guard_report_default = str(get_policy_value(policy, "paths.tools_dir", "prompt-dsl-system/tools") or "prompt-dsl-system/tools")
    guard_report_default = f"{guard_report_default}/guard_report.json"
    loop_report_default = f"{str(get_policy_value(policy, 'paths.tools_dir', 'prompt-dsl-system/tools') or 'prompt-dsl-system/tools')}/loop_diagnostics.json"
    move_report_default = f"{str(get_policy_value(policy, 'paths.tools_dir', 'prompt-dsl-system/tools') or 'prompt-dsl-system/tools')}/move_report.json"
    verify_report_default = f"{str(get_policy_value(policy, 'paths.tools_dir', 'prompt-dsl-system/tools') or 'prompt-dsl-system/tools')}/followup_verify_report.json"
    token_out_default = f"{str(get_policy_value(policy, 'paths.tools_dir', 'prompt-dsl-system/tools') or 'prompt-dsl-system/tools')}/RISK_GATE_TOKEN.txt"
    token_json_default = f"{str(get_policy_value(policy, 'paths.tools_dir', 'prompt-dsl-system/tools') or 'prompt-dsl-system/tools')}/RISK_GATE_TOKEN.json"
    json_out_default = f"{str(get_policy_value(policy, 'paths.tools_dir', 'prompt-dsl-system/tools') or 'prompt-dsl-system/tools')}/risk_gate_report.json"
    verify_threshold_default = "FAIL" if parse_bool(get_policy_value(policy, "gates.verify_gate.fail_on_fail", True), default=True) else "WARN"
    threshold_default = "HIGH"
    ttl_default = 30
    exit_code_default = 4
    allow_ack_on_fail = parse_bool(get_policy_value(policy, "gates.verify_gate.allow_ack_on_fail", False), default=False)

    guard_report_path = to_repo_path(repo_root, str(args.guard_report or "").strip() or guard_report_default)
    loop_report_path = to_repo_path(repo_root, str(args.loop_report or "").strip() or loop_report_default)
    move_report_path = to_repo_path(repo_root, str(args.move_report or "").strip() or move_report_default)
    verify_report_path = to_repo_path(repo_root, str(args.verify_report or "").strip() or verify_report_default)
    scan_report_path = to_repo_path(repo_root, args.scan_report) if str(args.scan_report).strip() else None
    patch_plan_path = to_repo_path(repo_root, args.patch_plan) if str(args.patch_plan).strip() else None
    token_out_path = to_repo_path(repo_root, str(args.token_out or "").strip() or token_out_default)
    token_json_out_path = to_repo_path(repo_root, str(args.token_json_out or "").strip() or token_json_default)
    json_out_path = to_repo_path(repo_root, str(args.json_out or "").strip() or json_out_default)

    threshold = risk_norm(str(args.threshold or "").strip() or threshold_default)
    ttl_minutes = parse_int(args.ttl_minutes, default=ttl_default, minimum=0)
    exit_code = parse_int(args.exit_code, default=exit_code_default, minimum=1)
    consume_on_pass = parse_bool(args.consume_on_pass, default=True)
    verify_as_risk = parse_bool(args.verify_as_risk, default=True)
    verify_threshold = (str(args.verify_threshold).strip().upper() if str(args.verify_threshold).strip() else verify_threshold_default)
    if verify_threshold not in VERIFY_RANK:
        verify_threshold = "FAIL"
    verify_required_for = [str(x).strip() for x in (args.verify_required_for or []) if str(x).strip()]
    command_name = str(args.command_name or "").strip()

    guard = safe_read_json(guard_report_path)
    loop = safe_read_json(loop_report_path)
    move_report = safe_read_json(move_report_path)
    verify_report = safe_read_json(verify_report_path)
    scan_report = safe_read_json(scan_report_path) if scan_report_path is not None else {}
    patch_plan = safe_read_json(patch_plan_path) if patch_plan_path is not None else {}

    guard_risk, guard_reasons, guard_evidence = build_guard_risk(guard)
    loop_risk, loop_reasons, loop_evidence = build_loop_risk(loop)
    verify_gate_required, verify_gate_reason, verify_hits_total, verify_reasons, verify_evidence, verify_applies = build_verify_gate(
        verify_report=verify_report,
        verify_threshold=verify_threshold,
        verify_as_risk=verify_as_risk,
        verify_required_for=verify_required_for,
        command_name=command_name,
    )

    overall_risk = max_risk(guard_risk, loop_risk)
    if verify_gate_required and verify_as_risk:
        overall_risk = max_risk(overall_risk, "HIGH")

    guard_violation_types = parse_guard_violation_types(guard_evidence)
    move_info = load_move_report_info(move_report)
    auto_ack_allowed, auto_ack_denied_reason, move_blockers = decide_auto_ack(
        overall_risk=overall_risk,
        guard_violation_types=guard_violation_types,
        move_info=move_info,
    )
    loop_triggers = loop_evidence.get("loop_triggers") if isinstance(loop_evidence, dict) else []
    if not isinstance(loop_triggers, list):
        loop_triggers = []
    if "release_gate_bypass_attempt" in [str(x) for x in loop_triggers]:
        overall_risk = max_risk(overall_risk, "HIGH")
        auto_ack_allowed = False
        auto_ack_denied_reason = (
            "verification failed and repeated bypass attempts detected; manual ack required"
        )
        move_blockers = sorted(set(move_blockers + ["release_gate_bypass_attempt"]))

    if verify_gate_required:
        if allow_ack_on_fail:
            auto_ack_allowed = auto_ack_allowed and True
        else:
            auto_ack_allowed = False
            if not auto_ack_denied_reason:
                auto_ack_denied_reason = "release verification failed requires manual ack"
        if verify_gate_reason:
            move_blockers = sorted(set(move_blockers + [verify_gate_reason]))

    scan_moves = scan_report.get("moves")
    scan_moves_count = len(scan_moves) if isinstance(scan_moves, list) else 0
    patch_files = patch_plan.get("files")
    patch_files_count = len(patch_files) if isinstance(patch_files, list) else 0
    patch_total_replacements = parse_int(patch_plan.get("total_replacements"), default=0, minimum=0)
    extra_evidence: Dict[str, Any] = {
        "verify_report_path": to_repo_relative(verify_report_path, repo_root),
        "verify_report_digest": json_digest(verify_report),
        "verify_status": verify_evidence.get("verify_status"),
        "verify_hits_total": verify_evidence.get("verify_hits_total"),
        "verify_gate_required": verify_evidence.get("verify_gate_required"),
        "verify_threshold": verify_evidence.get("verify_threshold"),
        "verify_required_for": verify_evidence.get("verify_required_for"),
        "verify_command_name": verify_evidence.get("verify_command_name"),
        "verify_applies_to_command": verify_evidence.get("verify_applies_to_command"),
        "verify_as_risk": verify_evidence.get("verify_as_risk"),
        "scan_report_path": to_repo_relative(scan_report_path, repo_root) if scan_report_path else None,
        "scan_report_digest": json_digest(scan_report),
        "scan_moves_count": scan_moves_count,
        "patch_plan_path": to_repo_relative(patch_plan_path, repo_root) if patch_plan_path else None,
        "patch_plan_digest": json_digest(patch_plan),
        "patch_files_count": patch_files_count,
        "patch_total_replacements": patch_total_replacements,
    }

    reasons: List[str] = []
    reasons.extend(guard_reasons)
    reasons.extend(loop_reasons)
    reasons.extend(verify_reasons)
    if verify_evidence.get("verify_status") == "MISSING":
        reasons.append("verify report missing; recommendation: run verify-followup-fixes")
    if not reasons:
        reasons.append("no high-risk indicators from guard/loop")

    reason_hash = build_reason_hash(guard_evidence, loop_evidence, extra_evidence=extra_evidence)

    report_base: Dict[str, Any] = {
        "generated_at": iso(now_utc()),
        "repo_root": str(repo_root),
        "mode": args.mode,
        "threshold": threshold,
        "guard_report": str(guard_report_path),
        "loop_report": str(loop_report_path),
        "move_report": str(move_report_path),
        "verify_report": str(verify_report_path),
        "verify_threshold": verify_threshold,
        "verify_as_risk": bool(verify_as_risk),
        "verify_allow_ack_on_fail": bool(allow_ack_on_fail),
        "verify_required_for": sorted(set(verify_required_for)),
        "command_name": command_name or None,
        "scan_report": str(scan_report_path) if scan_report_path else None,
        "patch_plan": str(patch_plan_path) if patch_plan_path else None,
        "guard_risk": guard_risk,
        "loop_risk": loop_risk,
        "loop_triggers": loop_triggers,
        "overall_risk": overall_risk,
        "verify_status": verify_evidence.get("verify_status"),
        "verify_hits_total": verify_hits_total,
        "verify_gate_required": bool(verify_gate_required),
        "verify_gate_reason": verify_gate_reason if verify_gate_reason else None,
        "guard_violation_types": guard_violation_types,
        "auto_ack_allowed": bool(auto_ack_allowed),
        "auto_ack_denied_reason": auto_ack_denied_reason,
        "move_plan_available": bool(move_info.get("generated", False)),
        "move_plan_movable_ratio": move_info.get("movable_ratio"),
        "move_plan_high_risk": move_info.get("summary_high_risk"),
        "move_plan_blockers": move_blockers,
        "move_plan_generated_reason": move_info.get("generated_reason"),
        "reasons": reasons,
        "reason_hash": reason_hash,
        "token_out": str(token_out_path),
        "token_json_out": str(token_json_out_path),
        "json_out": str(json_out_path),
        "next_cmd": build_next_cmd_ack_latest(),
        "next_cmd_ack_file": build_next_cmd_ack_file(
            to_repo_relative(token_json_out_path, repo_root)
        ),
        "ack_provided": bool(args.ack),
        "acked": False,
        "ack_valid": False,
        "blocked": False,
        "evidence": {
            **guard_evidence,
            **loop_evidence,
            **extra_evidence,
        },
        "next_cmd_example": build_next_cmd_example("<TOKEN>"),
    }

    if RANK[overall_risk] < RANK[threshold]:
        json_out_path.parent.mkdir(parents=True, exist_ok=True)
        json_out_path.write_text(json.dumps(report_base, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[risk-gate] pass overall_risk={overall_risk} threshold={threshold}")
        return 0

    if args.mode == "issue":
        issued = issue_token(
            repo_root=repo_root,
            overall_risk=overall_risk,
            reasons=reasons,
            reason_hash=reason_hash,
            token_out=token_out_path,
            token_json_out=token_json_out_path,
            json_out=json_out_path,
            ttl_minutes=ttl_minutes,
            threshold=threshold,
            exit_code=exit_code,
        )
        merged = {**report_base, **issued}
        json_out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[risk-gate] blocked overall_risk={overall_risk} token={token_out_path}", flush=True)
        print("Risk gate blocked: acknowledgment required", flush=True)
        return exit_code

    if args.ack:
        ok, msg, prev = validate_ack(
            ack=args.ack,
            repo_root=repo_root,
            overall_risk=overall_risk,
            reason_hash=reason_hash,
            token_json_out=token_json_out_path,
            json_out=json_out_path,
            consume_on_pass=consume_on_pass,
        )
        if ok:
            report = {**report_base}
            report["acked"] = True
            report["ack_valid"] = True
            report["blocked"] = False
            report["token"] = {
                "value": prev.get("token"),
                "repo_root": prev.get("repo_root"),
                "overall_risk": prev.get("overall_risk"),
                "reason_hash": prev.get("reason_hash"),
                "issued_at": prev.get("issued_at"),
                "expires_at": prev.get("expires_at"),
                "consumed": prev.get("consumed", False),
                "consumed_at": prev.get("consumed_at"),
            }
            json_out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[risk-gate] pass overall_risk={overall_risk} acked=true")
            return 0

    issued = issue_token(
        repo_root=repo_root,
        overall_risk=overall_risk,
        reasons=reasons,
        reason_hash=reason_hash,
        token_out=token_out_path,
        token_json_out=token_json_out_path,
        json_out=json_out_path,
        ttl_minutes=ttl_minutes,
        threshold=threshold,
        exit_code=exit_code,
    )
    merged = {**report_base, **issued}
    merged["blocked"] = True
    merged["acked"] = False
    merged["ack_valid"] = False
    json_out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[risk-gate] blocked overall_risk={overall_risk} token={token_out_path}", flush=True)
    print("Risk gate blocked: acknowledgment required", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
