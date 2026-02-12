#!/usr/bin/env python3
"""Generate actionable health runbook from health_report.json.

Standard-library only, plan-generation only (no command execution).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from policy_loader import build_cli_override_dict, get_policy_value, load_policy

DEFAULT_HEALTH_REPORT = "prompt-dsl-system/tools/health_report.json"
DEFAULT_OUTPUT_DIR = "prompt-dsl-system/tools"

PLACEHOLDERS: Dict[str, Dict[str, str]] = {
    "REPO_ROOT": {
        "default": ".",
        "example": ".",
        "hint": "仓库根路径，通常用 '.'。",
    },
    "MODULE_PATH": {
        "default": "",
        "example": "prompt-dsl-system",
        "hint": "模块边界目录（绝对路径或相对 REPO_ROOT）。",
    },
    "PIPELINE_PATH": {
        "default": "",
        "example": "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md",
        "hint": "目标 pipeline markdown 路径。",
    },
    "MOVES_JSON": {
        "default": "",
        "example": "prompt-dsl-system/tools/moves_mapping_rename_suffix.json",
        "hint": "move mapping / move report 路径（verify-followup-fixes 输入）。",
    },
    "SCAN_REPORT_JSON": {
        "default": "",
        "example": "prompt-dsl-system/tools/followup_scan_report_rename_suffix.json",
        "hint": "followup 扫描报告路径（apply-followup-fixes 输入）。",
    },
}


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


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def to_repo_path(repo_root: Path, raw: str) -> Path:
    p = Path(raw)
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


def get_int(mapping: Dict[str, Any], key: str) -> int:
    raw = mapping.get(key)
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    try:
        return int(str(raw).strip())
    except Exception:
        return 0


def get_text(value: Any, fallback: str = "unknown") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    return text


def get_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def normalize_counter(raw: Any) -> Dict[str, int]:
    out: Dict[str, int] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        key = str(k).strip()
        if not key:
            continue
        out[key] = get_int(raw, k)
    return out


def bool_hint(value: bool) -> str:
    return "true" if value else "false"


def build_cmd(*parts: str) -> str:
    return " ".join(parts)


def step(
    sid: int,
    title: str,
    purpose: str,
    command: Optional[str],
    expected_output: str,
    if_blocked: str,
    placeholders: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "id": sid,
        "title": title,
        "purpose": purpose,
        "command": command,
        "expected_output": expected_output,
        "if_blocked": if_blocked,
        "placeholders": placeholders or [],
    }


def decide_steps(report: Dict[str, Any], mode: str, include_ack_flows: bool) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    build = report.get("build_integrity") if isinstance(report.get("build_integrity"), dict) else {}
    signals = report.get("execution_signals") if isinstance(report.get("execution_signals"), dict) else {}
    risk = report.get("risk_triggers") if isinstance(report.get("risk_triggers"), dict) else {}
    post_validate = report.get("post_validate_gates") if isinstance(report.get("post_validate_gates"), dict) else {}

    validate_errors = get_int(build, "errors")
    validate_warnings = get_int(build, "warnings")
    total_runs = get_int(signals, "total_runs")
    post_validate_overall_status = get_text(post_validate.get("overall_status"), fallback="UNKNOWN").upper()
    post_validate_gate_status_counter: Dict[str, int] = {}
    gates_raw = post_validate.get("gates")
    if isinstance(gates_raw, list):
        for item in gates_raw:
            if not isinstance(item, dict):
                continue
            status = get_text(item.get("status"), fallback="UNKNOWN").upper()
            post_validate_gate_status_counter[status] = post_validate_gate_status_counter.get(status, 0) + 1

    verify_dist = normalize_counter(signals.get("verify_status_distribution"))
    blocked_dist = normalize_counter(signals.get("blocked_by_distribution"))
    exit_dist = normalize_counter(signals.get("exit_code_distribution"))

    verify_fail_count = verify_dist.get("FAIL", 0)
    verify_fail_ratio = get_ratio(verify_fail_count, max(total_runs, 1))

    bypass_attempt_count = get_int(risk, "bypass_attempt_count")
    top_triggers = risk.get("top_triggers") if isinstance(risk.get("top_triggers"), list) else []

    guard_gate_count = blocked_dist.get("guard_gate", 0)
    loop_gate_count = blocked_dist.get("loop_gate", 0)
    verify_gate_count = blocked_dist.get("verify_gate", 0)

    dominant_block_type = "none"
    if guard_gate_count >= max(loop_gate_count, verify_gate_count) and guard_gate_count > 0:
        dominant_block_type = "guard_gate"
    elif loop_gate_count >= max(guard_gate_count, verify_gate_count) and loop_gate_count > 0:
        dominant_block_type = "loop_gate"
    elif verify_gate_count > 0:
        dominant_block_type = "verify_gate"

    ack_flow = (
        "查看 prompt-dsl-system/tools/RISK_GATE_TOKEN.json，然后手动重试并追加 --ack-latest（必要时追加 --ack-note）。"
        if include_ack_flows
        else "查看 risk gate 报告并人工决策后重试。"
    )

    steps: List[Dict[str, Any]] = []
    sid = 1

    # P0) post-validate gates fail => hard block first
    if post_validate_overall_status == "FAIL":
        steps.append(
            step(
                sid,
                "Post-Gate Block: Re-run Validate",
                "后置闸门失败优先阻断，先重跑 validate 刷新 post_validate_gates。",
                build_cmd("./prompt-dsl-system/tools/run.sh", "validate", "-r", '"${REPO_ROOT}"'),
                "validate 输出中应出现 [contract_replay] PASS 与 [template_guard] PASS。",
                "若仍 FAIL，执行下一步逐项排查，禁止推进 run/apply。",
            )
        )
        sid += 1
        steps.append(
            step(
                sid,
                "Replay Contract Samples",
                "验证机器合约样例链路是否完整。",
                build_cmd(
                    "bash",
                    "prompt-dsl-system/tools/contract_samples/replay_contract_samples.sh",
                    "--repo-root",
                    '"${REPO_ROOT}"',
                ),
                "输出 [contract_replay] PASS。",
                "若失败，先修复 contract schema/validator/sample，再回到 Step 1。",
            )
        )
        sid += 1
        steps.append(
            step(
                sid,
                "Run Template Guard",
                "验证 A3 收尾模板完整性与占位符契约。",
                build_cmd(
                    "/usr/bin/python3",
                    "prompt-dsl-system/tools/kit_self_upgrade_template_guard.py",
                    "--repo-root",
                    '"${REPO_ROOT}"',
                ),
                "输出 [template_guard] PASS。",
                "若失败，补齐 templates 后重跑 Step 1。",
            )
        )
        sid += 1
        steps.append(
            step(
                sid,
                "Stop Promotion Until Post-Gates PASS",
                "后置闸门未通过前禁止进入 run/apply/promotion。",
                None,
                "仅在 post_validate_gates.overall_status=PASS 后恢复常规 runbook。",
                "保持阻断并通知人工处理。",
            )
        )
        context = {
            "validate_errors": validate_errors,
            "validate_warnings": validate_warnings,
            "verify_fail_count": verify_fail_count,
            "verify_fail_ratio": round(verify_fail_ratio, 4),
            "bypass_attempt_count": bypass_attempt_count,
            "dominant_block_type": "post_validate_gates",
            "exit_code_distribution": exit_dist,
            "top_triggers": top_triggers,
            "post_validate_overall_status": post_validate_overall_status,
            "post_validate_gate_status_distribution": post_validate_gate_status_counter,
        }
        return steps, context

    # A) validate errors first
    if validate_errors > 0:
        steps.append(
            step(
                sid,
                "Re-run Validate",
                "先确认结构错误是否仍存在，并锁定 registry/pipeline 失败点。",
                build_cmd("./prompt-dsl-system/tools/run.sh", "validate", "-r", '"${REPO_ROOT}"'),
                "Validation Summary 输出 Errors/Warnings；保持 Errors=0 后再推进。",
                "先修复 validate_report.json 对应错误，不要直接推进 run/apply。",
            )
        )
        sid += 1
        steps.append(
            step(
                sid,
                "Stop Promotion Until Errors Cleared",
                "在 errors>0 场景下阻断推进，避免放大系统性问题。",
                None,
                "确认 Errors 清零后再进入 run plan 生成。",
                "修复后重新执行本 runbook 第 1 步。",
            )
        )
        sid += 1

    # B) bypass attempts
    if bypass_attempt_count >= 1:
        steps.append(
            step(
                sid,
                "Verify Residual References",
                "先把 verify FAIL 收敛到 PASS，终止 bypass 风险升级。",
                build_cmd(
                    "./prompt-dsl-system/tools/run.sh",
                    "verify-followup-fixes",
                    "-r",
                    '"${REPO_ROOT}"',
                    "--moves",
                    '"${MOVES_JSON}"',
                ),
                "生成/更新 followup_verify_report.json，目标 status=PASS。",
                "先确认 MOVES_JSON 正确；若 risk gate 阻断，" + ack_flow,
                placeholders=["MOVES_JSON"],
            )
        )
        sid += 1
        steps.append(
            step(
                sid,
                "Run Plan (No ACK Auto)",
                "仅做计划生成，验证当前是否还能无风险推进。",
                build_cmd(
                    "./prompt-dsl-system/tools/run.sh",
                    "run",
                    "-r",
                    '"${REPO_ROOT}"',
                    "-m",
                    '"${MODULE_PATH}"',
                    "--pipeline",
                    '"${PIPELINE_PATH}"',
                ),
                "生成 run_plan.yaml 或被 gate 阻断并给出 token。",
                "不要直接强推；先把 verify FAIL 修复到 PASS 后再考虑 ACK。",
                placeholders=["MODULE_PATH", "PIPELINE_PATH"],
            )
        )
        sid += 1
        steps.append(
            step(
                sid,
                "ACK Note Guidance",
                "如确需临时放行，先记录人工理由保证审计可追溯。",
                None,
                "建议命令示例：... --ack-latest --ack-note \"<reason>\"",
                "仅在业务窗口紧急且影响已评估时使用。",
            )
        )
        sid += 1

    # C) verify fail trend
    if verify_fail_count > 0:
        steps.append(
            step(
                sid,
                "Verify Until PASS",
                "持续验证残留引用，直到 verify 报告为 PASS。",
                build_cmd(
                    "./prompt-dsl-system/tools/run.sh",
                    "verify-followup-fixes",
                    "-r",
                    '"${REPO_ROOT}"',
                    "--moves",
                    '"${MOVES_JSON}"',
                ),
                "followup_verify_report.json 状态收敛到 PASS。",
                "若报告 FAIL/WARN，继续下一步补丁 plan。",
                placeholders=["MOVES_JSON"],
            )
        )
        sid += 1
        steps.append(
            step(
                sid,
                "Generate Follow-up Patch Plan",
                "只生成补丁计划，不直接改文件。",
                build_cmd(
                    "./prompt-dsl-system/tools/run.sh",
                    "apply-followup-fixes",
                    "-r",
                    '"${REPO_ROOT}"',
                    "--scan-report",
                    '"${SCAN_REPORT_JSON}"',
                    "--mode",
                    "plan",
                ),
                "生成 followup_patch_plan.* 与 followup_patch.diff。",
                "修正 SCAN_REPORT_JSON 路径后重试。",
                placeholders=["SCAN_REPORT_JSON"],
            )
        )
        sid += 1
        if mode == "aggressive":
            steps.append(
                step(
                    sid,
                    "(Aggressive) Prepare Apply Command",
                    "给出 apply 命令模板（默认 dry-run=true，不会执行修改）。",
                    build_cmd(
                        "./prompt-dsl-system/tools/run.sh",
                        "apply-followup-fixes",
                        "-r",
                        '"${REPO_ROOT}"',
                        "--scan-report",
                        '"${SCAN_REPORT_JSON}"',
                        "--mode",
                        "apply",
                        "--yes",
                        "--dry-run",
                        "true",
                    ),
                    "仅演练命令链路；真正执行需 --dry-run false 且 ACK。",
                    "若需真实执行，请人工评审后手动切换 --dry-run false。",
                    placeholders=["SCAN_REPORT_JSON"],
                )
            )
            sid += 1
        steps.append(
            step(
                sid,
                "Re-Verify",
                "再次验证补丁计划后的残留状态。",
                build_cmd(
                    "./prompt-dsl-system/tools/run.sh",
                    "verify-followup-fixes",
                    "-r",
                    '"${REPO_ROOT}"',
                    "--moves",
                    '"${MOVES_JSON}"',
                ),
                "目标 status=PASS；FAIL 则回到补丁 plan 循环。",
                "持续 FAIL 时先做 debug-guard + move plan 收敛边界问题。",
                placeholders=["MOVES_JSON"],
            )
        )
        sid += 1

    # D) guard/outside-module dominated
    if dominant_block_type == "guard_gate":
        steps.append(
            step(
                sid,
                "Debug Guard",
                "先看越界与 forbidden 命中点，生成 move/rollback 方案。",
                build_cmd(
                    "./prompt-dsl-system/tools/run.sh",
                    "debug-guard",
                    "-r",
                    '"${REPO_ROOT}"',
                    "-m",
                    '"${MODULE_PATH}"',
                ),
                "生成 guard_report + move_plan + rollback_plan。",
                "若 module_path 无效，先修正 MODULE_PATH。",
                placeholders=["MODULE_PATH"],
            )
        )
        sid += 1
        steps.append(
            step(
                sid,
                "Apply Move (Plan Only)",
                "先生成迁移执行计划，不执行移动。",
                build_cmd(
                    "./prompt-dsl-system/tools/run.sh",
                    "apply-move",
                    "-r",
                    '"${REPO_ROOT}"',
                    "-m",
                    '"${MODULE_PATH}"',
                ),
                "无违规时会提示 no violations；有冲突会生成 conflict_plan。",
                "如冲突 dst exists，进入下一步冲突策略 plan。",
                placeholders=["MODULE_PATH"],
            )
        )
        sid += 1
        steps.append(
            step(
                sid,
                "Resolve Move Conflicts (Plan)",
                "冲突场景先选策略生成计划，不执行 apply。",
                build_cmd(
                    "./prompt-dsl-system/tools/run.sh",
                    "resolve-move-conflicts",
                    "-r",
                    '"${REPO_ROOT}"',
                    "-m",
                    '"${MODULE_PATH}"',
                    "--strategy",
                    "rename_suffix",
                    "--mode",
                    "plan",
                ),
                "生成 conflict_plan 与策略脚本。",
                "若仍有高风险 blocker，先人工处理后再尝试 apply。",
                placeholders=["MODULE_PATH"],
            )
        )
        sid += 1

    # E) loop gate dominated
    if dominant_block_type == "loop_gate":
        steps.append(
            step(
                sid,
                "Validate Baseline",
                "先确认结构层无新增错误。",
                build_cmd("./prompt-dsl-system/tools/run.sh", "validate", "-r", '"${REPO_ROOT}"'),
                "Errors=0 Warnings=0。",
                "若失败，先修 validate 错误再跑 run。",
            )
        )
        sid += 1
        steps.append(
            step(
                sid,
                "Run With Loop Gate",
                "开启 fail-on-loop，避免在同类失败上反复试错。",
                build_cmd(
                    "./prompt-dsl-system/tools/run.sh",
                    "run",
                    "-r",
                    '"${REPO_ROOT}"',
                    "-m",
                    '"${MODULE_PATH}"',
                    "--pipeline",
                    '"${PIPELINE_PATH}"',
                    "--fail-on-loop",
                ),
                "若触发 loop HIGH 将直接阻断并输出计划。",
                "优先看 loop_diagnostics.md + guard_report.json 再继续。",
                placeholders=["MODULE_PATH", "PIPELINE_PATH"],
            )
        )
        sid += 1
        steps.append(
            step(
                sid,
                "Reduce Loop Surface",
                "减少同文件来回修改；先做依赖链路梳理或 change ledger。",
                None,
                "形成可审计的变更范围与回滚点后再推进。",
                "必要时先停下请求人工介入。",
            )
        )
        sid += 1

    # fallback minimal path
    if not steps:
        steps.append(
            step(
                sid,
                "Validate",
                "基线校验并刷新 health_report。",
                build_cmd("./prompt-dsl-system/tools/run.sh", "validate", "-r", '"${REPO_ROOT}"'),
                "Errors=0 Warnings=0。",
                "若被 gate 阻断，按 token 流程手工确认后重试。",
            )
        )
        sid += 1
        steps.append(
            step(
                sid,
                "Generate Run Plan",
                "按模块边界生成 run_plan，不做业务改动。",
                build_cmd(
                    "./prompt-dsl-system/tools/run.sh",
                    "run",
                    "-r",
                    '"${REPO_ROOT}"',
                    "-m",
                    '"${MODULE_PATH}"',
                    "--pipeline",
                    '"${PIPELINE_PATH}"',
                ),
                "生成 run_plan.yaml。",
                "如果被 risk/verify gate 阻断，先按 health_report 建议收敛再推进。",
                placeholders=["MODULE_PATH", "PIPELINE_PATH"],
            )
        )

    context = {
        "validate_errors": validate_errors,
        "validate_warnings": validate_warnings,
        "verify_fail_count": verify_fail_count,
        "verify_fail_ratio": round(verify_fail_ratio, 4),
        "bypass_attempt_count": bypass_attempt_count,
        "dominant_block_type": dominant_block_type,
        "exit_code_distribution": exit_dist,
        "top_triggers": top_triggers,
        "post_validate_overall_status": post_validate_overall_status,
        "post_validate_gate_status_distribution": post_validate_gate_status_counter,
    }
    return steps, context


def build_runbook_json(
    repo_root: Path,
    health_report_path: Path,
    mode: str,
    include_ack_flows: bool,
    health_report: Dict[str, Any],
    steps: Sequence[Dict[str, Any]],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "generated_at": now_iso(),
        "mode": mode,
        "repo_root": str(repo_root),
        "source_health_report": to_repo_relative(health_report_path, repo_root),
        "include_ack_flows": include_ack_flows,
        "placeholders": {
            key: {
                "default": meta["default"],
                "example": meta["example"],
                "hint": meta["hint"],
            }
            for key, meta in PLACEHOLDERS.items()
        },
        "decision_context": context,
        "health_summary": {
            "build_integrity": health_report.get("build_integrity", {}),
            "execution_signals": health_report.get("execution_signals", {}),
            "risk_triggers": health_report.get("risk_triggers", {}),
            "post_validate_gates": health_report.get("post_validate_gates", {}),
        },
        "steps": list(steps),
    }


def write_runbook_md(path: Path, runbook: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# Health Runbook")
    lines.append(f"- Generated at: {runbook.get('generated_at')}")
    lines.append(f"- Mode: {runbook.get('mode')}")
    lines.append(f"- Repo root: {runbook.get('repo_root')}")
    lines.append("")
    lines.append("## Fill-in Guide (replace placeholders)")
    placeholders = runbook.get("placeholders", {})
    if isinstance(placeholders, dict):
        for key in ["MODULE_PATH", "PIPELINE_PATH", "MOVES_JSON", "SCAN_REPORT_JSON", "REPO_ROOT"]:
            meta = placeholders.get(key)
            if not isinstance(meta, dict):
                continue
            lines.append(f"- <{key}>: {meta.get('hint')}")
            lines.append(f"  - Example: `{meta.get('example')}`")
    lines.append("")
    lines.append("## Recommended Path (Shortest)")

    steps = runbook.get("steps") if isinstance(runbook.get("steps"), list) else []
    for item in steps:
        if not isinstance(item, dict):
            continue
        lines.append(f"### Step {item.get('id')} — {item.get('title')}")
        lines.append(f"- Purpose: {item.get('purpose')}")
        cmd = item.get("command")
        if isinstance(cmd, str) and cmd.strip():
            lines.append("```bash")
            lines.append(cmd)
            lines.append("```")
        else:
            lines.append("```bash")
            lines.append("# (no direct command; manual decision point)")
            lines.append("```")
        lines.append(f"- Expected output: {item.get('expected_output')}")
        lines.append(f"- If blocked: {item.get('if_blocked')}")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_runbook_sh(path: Path, runbook: Dict[str, Any], shell: str) -> None:
    shell_name = "bash" if shell not in {"bash", "zsh"} else shell
    shebang = "#!/usr/bin/env bash" if shell_name == "bash" else "#!/usr/bin/env zsh"

    steps = runbook.get("steps") if isinstance(runbook.get("steps"), list) else []

    required_vars = {"MODULE_PATH"}  # hard requirement per spec
    for item in steps:
        if not isinstance(item, dict):
            continue
        for ph in item.get("placeholders", []):
            required_vars.add(str(ph))

    lines: List[str] = []
    lines.append(shebang)
    lines.append("set -euo pipefail")
    lines.append("")
    lines.append('REPO_ROOT="${REPO_ROOT:-.}"')
    lines.append('MODULE_PATH="${MODULE_PATH:-}"')
    lines.append('PIPELINE_PATH="${PIPELINE_PATH:-}"')
    lines.append('MOVES_JSON="${MOVES_JSON:-}"')
    lines.append('SCAN_REPORT_JSON="${SCAN_REPORT_JSON:-}"')
    lines.append("")
    lines.append("require_var() {")
    lines.append("  local name=\"$1\"")
    lines.append("  local value=\"$2\"")
    lines.append("  if [ -z \"$value\" ]; then")
    lines.append("    echo \"[ERROR] $name is required. Export $name first.\" >&2")
    lines.append("    exit 2")
    lines.append("  fi")
    lines.append("}")
    lines.append("")

    # Always enforce MODULE_PATH as requested.
    lines.append('require_var "MODULE_PATH" "$MODULE_PATH"')
    for key in ["PIPELINE_PATH", "MOVES_JSON", "SCAN_REPORT_JSON"]:
        if key in required_vars:
            lines.append(f'require_var "{key}" "${key}"')
    lines.append("")
    lines.append("echo \"[health-runbook] mode=${RUNBOOK_MODE:-safe} repo_root=${REPO_ROOT}\"")
    lines.append("")

    for item in steps:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "Step"))
        purpose = str(item.get("purpose", ""))
        cmd = item.get("command")
        lines.append(f'echo "[STEP {item.get("id")}] {title}"')
        if purpose:
            lines.append(f'echo "Purpose: {purpose}"')
        if isinstance(cmd, str) and cmd.strip():
            lines.append(cmd)
        else:
            lines.append('echo "Manual step: no direct command in this stage."')
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    try:
        path.chmod(0o755)
    except OSError:
        pass


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate health runbook from health_report.json")
    p.add_argument("--repo-root", required=True, help="Repository root")
    p.add_argument("--policy", default="", help="Optional policy YAML path")
    p.add_argument("--policy-override", action="append", default=[], help="Policy override key=value")
    p.add_argument("--health-report", default="")
    p.add_argument("--output-dir", default="")
    p.add_argument("--mode", default="", choices=["safe", "aggressive", ""])
    p.add_argument("--include-ack-flows", default="true")
    p.add_argument("--shell", default="bash", choices=["bash", "zsh"])
    p.add_argument("--emit-sh", default="true")
    p.add_argument("--emit-md", default="true")
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

    health_report_default = str(get_policy_value(policy, "paths.health_report_json", DEFAULT_HEALTH_REPORT) or DEFAULT_HEALTH_REPORT)
    output_dir_default = str(get_policy_value(policy, "paths.tools_dir", DEFAULT_OUTPUT_DIR) or DEFAULT_OUTPUT_DIR)
    mode_default = str(get_policy_value(policy, "health.runbook_mode", "safe") or "safe").strip().lower()
    if mode_default not in {"safe", "aggressive"}:
        mode_default = "safe"

    health_report_path = to_repo_path(repo_root, str(args.health_report or "").strip() or health_report_default)
    output_dir = to_repo_path(repo_root, str(args.output_dir or "").strip() or output_dir_default)
    output_dir.mkdir(parents=True, exist_ok=True)

    health_report = safe_read_json(health_report_path)
    if not health_report:
        print(f"health report not found or invalid: {health_report_path}", file=sys.stderr)
        return 2

    mode = str(args.mode or "").strip().lower() or mode_default
    if mode not in {"safe", "aggressive"}:
        mode = "safe"

    include_ack_flows = parse_bool(args.include_ack_flows, default=True)
    emit_md = parse_bool(args.emit_md, default=True)
    emit_sh = parse_bool(args.emit_sh, default=True)
    shell = str(args.shell).strip().lower()
    if shell not in {"bash", "zsh"}:
        shell = "bash"

    steps, context = decide_steps(
        report=health_report,
        mode=mode,
        include_ack_flows=include_ack_flows,
    )

    runbook = build_runbook_json(
        repo_root=repo_root,
        health_report_path=health_report_path,
        mode=mode,
        include_ack_flows=include_ack_flows,
        health_report=health_report,
        steps=steps,
        context=context,
    )

    json_path = (output_dir / "health_runbook.json").resolve()
    md_path = (output_dir / "health_runbook.md").resolve()
    sh_path = (output_dir / "health_runbook.sh").resolve()

    json_path.write_text(json.dumps(runbook, ensure_ascii=False, indent=2), encoding="utf-8")
    if emit_md:
        write_runbook_md(md_path, runbook)
    if emit_sh:
        write_runbook_sh(sh_path, runbook, shell=shell)

    print(f"health_runbook_json: {to_repo_relative(json_path, repo_root)}")
    if emit_md:
        print(f"health_runbook_md: {to_repo_relative(md_path, repo_root)}")
    if emit_sh:
        print(f"health_runbook_sh: {to_repo_relative(sh_path, repo_root)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
