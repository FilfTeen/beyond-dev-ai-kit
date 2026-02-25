#!/usr/bin/env python3
"""Audit agent capability coverage and pressure efficiency for beyond-dev-ai-kit."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from intent_router import choose_action

TOOL = "agent_capability_audit"
TOOL_VERSION = "1.0.0"
EXIT_INVALID_INPUT = 2
EXIT_AUDIT_GATE_FAIL = 52

LEVEL_RANK = {
    "low": 0,
    "medium": 1,
    "high": 2,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def score_to_level(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"


def parse_level(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    return value if value in LEVEL_RANK else "low"


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


def check_paths(repo_root: Path, required_paths: Sequence[str]) -> Tuple[float, List[Dict[str, Any]], List[str]]:
    checks: List[Dict[str, Any]] = []
    missing: List[str] = []
    found = 0
    for rel in required_paths:
        exists = (repo_root / rel).exists()
        checks.append({"path": rel, "exists": bool(exists)})
        if exists:
            found += 1
        else:
            missing.append(rel)
    score = (found / len(required_paths)) if required_paths else 1.0
    return score, checks, missing


def read_text(repo_root: Path, rel_path: str) -> str:
    path = repo_root / rel_path
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def run_signal_checks(
    repo_root: Path,
    rules: Sequence[Tuple[str, str, str]],
) -> Tuple[float, List[Dict[str, Any]], List[str]]:
    checks: List[Dict[str, Any]] = []
    missing: List[str] = []
    found = 0
    for rel_path, marker, name in rules:
        text = read_text(repo_root, rel_path)
        ok = marker in text
        checks.append(
            {
                "name": name,
                "path": rel_path,
                "marker": marker,
                "found": bool(ok),
            }
        )
        if ok:
            found += 1
        else:
            missing.append(name)
    score = (found / len(rules)) if rules else 1.0
    return score, checks, missing


def evaluate_coverage(repo_root: Path) -> Dict[str, Any]:
    groups: Dict[str, Dict[str, Any]] = {
        "agent_usage_enablement": {
            "required_paths": [
                "AGENTS.md",
                "AGENTS.zh-CN.md",
                "prompt-dsl-system/tools/run.sh",
                "prompt-dsl-system/tools/intent_router.py",
                "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md",
            ],
            "signal_rules": [
                ("prompt-dsl-system/tools/run.sh", "[ \"$subcommand\" = \"intent\" ]", "run_sh_intent_entry"),
                ("prompt-dsl-system/tools/intent_router.py", "run_command", "router_run_command_output"),
                ("prompt-dsl-system/tools/intent_router.py", "can_auto_execute", "router_auto_execute_gate"),
            ],
        },
        "agent_proactive_sensing": {
            "required_paths": [
                "prompt-dsl-system/tools/kit_selfcheck.py",
                "prompt-dsl-system/tools/loop_detector.py",
                "prompt-dsl-system/tools/risk_gate.py",
                "prompt-dsl-system/tools/calibration_engine.py",
                "prompt-dsl-system/tools/scan_graph.py",
            ],
            "signal_rules": [
                ("prompt-dsl-system/tools/kit_selfcheck.py", "recommendations", "selfcheck_recommendations_channel"),
                ("prompt-dsl-system/tools/loop_detector.py", "loop", "loop_detector_enabled"),
                ("prompt-dsl-system/tools/risk_gate.py", "overall_risk", "risk_gate_summary_signal"),
            ],
        },
        "agent_proactive_invocation": {
            "required_paths": [
                "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md",
                "prompt-dsl-system/tools/pipeline_runner.py",
                "prompt-dsl-system/05_skill_registry/skills/universal/skill_hongzhi_universal_ops.yaml",
                "prompt-dsl-system/tools/tests/intent_router/intent_router_pressure.py",
            ],
            "signal_rules": [
                (
                    "prompt-dsl-system/tools/intent_router.py",
                    "detect_kit_self_upgrade_intent",
                    "router_kit_upgrade_detector",
                ),
                (
                    "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md",
                    "A0_authority_alignment.md",
                    "pipeline_authority_alignment_step",
                ),
                (
                    "prompt-dsl-system/tools/tests/intent_router/intent_router_pressure.py",
                    "concurrent-calls",
                    "pressure_test_concurrency_control",
                ),
            ],
        },
    }

    dimensions: Dict[str, Any] = {}
    recommendations: List[str] = []

    for name, cfg in groups.items():
        file_score, file_checks, file_missing = check_paths(
            repo_root, cfg.get("required_paths", [])
        )
        signal_score, signal_checks, signal_missing = run_signal_checks(
            repo_root, cfg.get("signal_rules", [])
        )
        score = (file_score * 0.6) + (signal_score * 0.4)
        dimensions[name] = {
            "score": round(score, 3),
            "level": score_to_level(score),
            "file_score": round(file_score, 3),
            "signal_score": round(signal_score, 3),
            "file_checks": file_checks,
            "signal_checks": signal_checks,
            "file_missing": file_missing,
            "signal_missing": signal_missing,
        }
        if file_missing:
            recommendations.append(f"{name}: add missing files ({len(file_missing)}).")
        if signal_missing:
            recommendations.append(f"{name}: strengthen runtime signals ({len(signal_missing)}).")

    dim_scores = [float(item.get("score", 0.0)) for item in dimensions.values()]
    overall_score = (sum(dim_scores) / len(dim_scores)) if dim_scores else 0.0
    return {
        "summary": {
            "overall_score": round(overall_score, 3),
            "overall_level": score_to_level(overall_score),
            "dimension_count": len(dimensions),
        },
        "dimensions": dimensions,
        "recommendations": recommendations,
    }


def evaluate_route_probes(repo_root: Path) -> Dict[str, Any]:
    probes = [
        {
            "goal": "beyond-dev-ai-kit 以 agent 使用、主动感知、主动调用为核心，验证覆盖度完整性并做并发高压测试后升级",
            "expect_target_suffix": "pipeline_kit_self_upgrade.md",
        },
        {
            "goal": "基于最新创建提示词改进 beyond-dev-ai-kit 的 prompt/DSL/skill/pipeline 套件并落地",
            "expect_target_suffix": "pipeline_kit_self_upgrade.md",
        },
        {
            "goal": "升级 beyond-dev-ai-kit 套件并增强 agent 主动调用和高压测试能力",
            "expect_target_suffix": "pipeline_kit_self_upgrade.md",
        },
    ]

    checks: List[Dict[str, Any]] = []
    passed = 0
    for item in probes:
        routed = choose_action(goal_raw=item["goal"], repo_root=repo_root)
        selected = routed.get("selected", {})
        target = str(selected.get("target", ""))
        ok = target.endswith(item["expect_target_suffix"])
        checks.append(
            {
                "goal": item["goal"],
                "target": target,
                "selection_mode": selected.get("selection_mode"),
                "confidence": selected.get("confidence"),
                "passed": bool(ok),
            }
        )
        if ok:
            passed += 1

    score = (passed / len(probes)) if probes else 1.0
    return {
        "score": round(score, 3),
        "level": score_to_level(score),
        "checks": checks,
        "passed_count": passed,
        "total": len(probes),
    }


def run_pressure_test(
    repo_root: Path,
    single_calls: int,
    concurrent_calls: int,
    concurrency: int,
    max_p99_ms: float,
) -> Dict[str, Any]:
    pressure_script = repo_root / "prompt-dsl-system/tools/tests/intent_router/intent_router_pressure.py"
    with tempfile.TemporaryDirectory(prefix="agent-cap-audit-") as tmp:
        out_json = Path(tmp) / "intent_router_pressure.json"
        cmd = [
            "/usr/bin/python3",
            str(pressure_script),
            "--repo-root",
            str(repo_root),
            "--single-calls",
            str(int(single_calls)),
            "--concurrent-calls",
            str(int(concurrent_calls)),
            "--concurrency",
            str(int(concurrency)),
            "--max-p99-ms",
            str(float(max_p99_ms)),
            "--out-json",
            str(out_json),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        payload: Dict[str, Any] = {}
        if out_json.is_file():
            try:
                payload = json.loads(out_json.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                payload = {}

    concurrent_seconds = float(payload.get("concurrent_seconds", 0.0) or 0.0)
    concurrent_calls_value = int(payload.get("concurrent_calls", 0) or 0)
    qps = (concurrent_calls_value / concurrent_seconds) if concurrent_seconds > 0 else 0.0
    p99 = float(payload.get("single_thread_latency_ms", {}).get("p99", 0.0) or 0.0)
    single_errors = int(payload.get("single_thread_errors", 1) or 0)
    concurrent_errors = int(payload.get("concurrent_errors", 1) or 0)
    long_input_ok = bool(payload.get("long_input_ok", False))

    score = 1.0
    if single_errors > 0 or concurrent_errors > 0:
        score -= 0.35
    if p99 > max_p99_ms:
        score -= 0.25
    if qps < 250.0:
        score -= 0.2
    if not long_input_ok:
        score -= 0.2
    score = max(0.0, min(1.0, score))

    return {
        "returncode": int(proc.returncode),
        "score": round(score, 3),
        "level": score_to_level(score),
        "max_p99_ms": float(max_p99_ms),
        "qps": round(qps, 3),
        "report": payload,
        "stdout_tail": str(proc.stdout or "").strip().splitlines()[-3:],
        "stderr_tail": str(proc.stderr or "").strip().splitlines()[-3:],
    }


def render_markdown(report: Dict[str, Any]) -> str:
    summary = report.get("summary", {})
    coverage = report.get("coverage", {})
    coverage_summary = coverage.get("summary", {})
    route_probes = report.get("route_probes", {})
    pressure = report.get("pressure_test", {})

    lines: List[str] = []
    lines.append("# Agent Capability Audit")
    lines.append("")
    lines.append(f"- generated_at: `{report.get('generated_at', '-')}`")
    lines.append(f"- repo_root: `{report.get('repo_root', '-')}`")
    lines.append(f"- overall_score: `{summary.get('overall_score', 0)}`")
    lines.append(f"- overall_level: `{summary.get('overall_level', '-')}`")
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    lines.append(f"- coverage_score: `{coverage_summary.get('overall_score', 0)}`")
    lines.append(f"- coverage_level: `{coverage_summary.get('overall_level', '-')}`")
    lines.append(f"- coverage_dimensions: `{coverage_summary.get('dimension_count', 0)}`")
    lines.append("")
    lines.append("| Dimension | Score | Level |")
    lines.append("|---|---:|---|")
    for name, item in sorted((coverage.get("dimensions") or {}).items()):
        lines.append(f"| {name} | {item.get('score', 0)} | {item.get('level', '-')} |")

    lines.append("")
    lines.append("## Route Probes")
    lines.append("")
    lines.append(
        f"- route_probe_passed: `{route_probes.get('passed_count', 0)}/{route_probes.get('total', 0)}` score=`{route_probes.get('score', 0)}`"
    )
    for item in route_probes.get("checks", []):
        lines.append(
            f"- [{'PASS' if item.get('passed') else 'FAIL'}] target=`{item.get('target', '-')}` mode=`{item.get('selection_mode', '-')}`"
        )

    lines.append("")
    lines.append("## Pressure")
    lines.append("")
    lines.append(f"- pressure_score: `{pressure.get('score', 0)}` level=`{pressure.get('level', '-')}`")
    lines.append(f"- concurrent_qps: `{pressure.get('qps', 0)}`")
    lines.append(f"- pressure_returncode: `{pressure.get('returncode', -1)}`")
    pressure_report = pressure.get("report", {})
    if isinstance(pressure_report, dict):
        lat = pressure_report.get("single_thread_latency_ms", {})
        lines.append(
            f"- single_latency_ms p95=`{lat.get('p95', 0)}` p99=`{lat.get('p99', 0)}` max=`{lat.get('max', 0)}`"
        )
        lines.append(
            f"- errors single=`{pressure_report.get('single_thread_errors', 0)}` concurrent=`{pressure_report.get('concurrent_errors', 0)}`"
        )

    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    recommendations = report.get("recommendations", [])
    if recommendations:
        for rec in recommendations:
            lines.append(f"- {rec}")
    else:
        lines.append("- none")

    return "\n".join(lines)


def build_report(
    repo_root: Path,
    single_calls: int,
    concurrent_calls: int,
    concurrency: int,
    max_p99_ms: float,
    skip_pressure: bool,
) -> Dict[str, Any]:
    coverage = evaluate_coverage(repo_root)
    route_probes = evaluate_route_probes(repo_root)
    pressure = (
        {
            "score": 0.0,
            "level": "low",
            "returncode": -1,
            "report": {},
            "qps": 0.0,
        }
        if skip_pressure
        else run_pressure_test(
            repo_root=repo_root,
            single_calls=single_calls,
            concurrent_calls=concurrent_calls,
            concurrency=concurrency,
            max_p99_ms=max_p99_ms,
        )
    )

    coverage_score = float(coverage.get("summary", {}).get("overall_score", 0.0))
    route_score = float(route_probes.get("score", 0.0))
    pressure_score = float(pressure.get("score", 0.0))

    overall_score = (coverage_score * 0.45) + (route_score * 0.25) + (pressure_score * 0.30)
    recommendations: List[str] = []
    recommendations.extend(coverage.get("recommendations", []))
    if route_score < 1.0:
        recommendations.append("route_probes: align intent routing for agent proactive-upgrade goals.")
    if not skip_pressure and int(pressure.get("returncode", 1)) != 0:
        recommendations.append("pressure_test: stabilize concurrency/latency invariants before release.")
    if not skip_pressure and float(pressure.get("qps", 0.0)) < 300.0:
        recommendations.append("pressure_test: optimize route throughput (target concurrent qps >= 300).")

    return {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "summary": {
            "overall_score": round(overall_score, 3),
            "overall_level": score_to_level(overall_score),
            "coverage_score": round(coverage_score, 3),
            "route_probe_score": round(route_score, 3),
            "pressure_score": round(pressure_score, 3),
        },
        "coverage": coverage,
        "route_probes": route_probes,
        "pressure_test": pressure,
        "recommendations": recommendations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit agent-oriented coverage/completeness and pressure efficiency"
    )
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--single-calls", type=int, default=12000)
    parser.add_argument("--concurrent-calls", type=int, default=16000)
    parser.add_argument("--concurrency", type=int, default=48)
    parser.add_argument("--max-p99-ms", type=float, default=12.0)
    parser.add_argument("--skip-pressure", action="store_true")
    parser.add_argument("--min-overall-score", type=float, default=0.0)
    parser.add_argument(
        "--min-overall-level",
        choices=sorted(LEVEL_RANK.keys()),
        default="low",
    )
    parser.add_argument(
        "--require-pressure-pass",
        default="false",
        help="When true, require pressure_test.returncode == 0",
    )
    parser.add_argument(
        "--out-json",
        default="prompt-dsl-system/tools/agent_capability_audit.json",
    )
    parser.add_argument(
        "--out-md",
        default="prompt-dsl-system/tools/agent_capability_audit.md",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[{TOOL}] FAIL: invalid repo_root: {repo_root}")
        return EXIT_INVALID_INPUT
    if float(args.min_overall_score) < 0.0 or float(args.min_overall_score) > 1.0:
        print(f"[{TOOL}] FAIL: min-overall-score out of range [0,1]: {args.min_overall_score}")
        return EXIT_INVALID_INPUT

    report = build_report(
        repo_root=repo_root,
        single_calls=max(1, int(args.single_calls)),
        concurrent_calls=max(1, int(args.concurrent_calls)),
        concurrency=max(1, int(args.concurrency)),
        max_p99_ms=max(1.0, float(args.max_p99_ms)),
        skip_pressure=bool(args.skip_pressure),
    )
    markdown = render_markdown(report)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not out_json.is_absolute():
        out_json = (repo_root / out_json).resolve()
    if not out_md.is_absolute():
        out_md = (repo_root / out_md).resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(markdown + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[{TOOL}] json={out_json}")
    print(f"[{TOOL}] md={out_md}")

    min_score = float(args.min_overall_score)
    min_level = parse_level(args.min_overall_level)
    require_pressure_pass = parse_bool(args.require_pressure_pass, default=False)
    summary = report.get("summary", {})
    actual_score = float(summary.get("overall_score", 0.0))
    actual_level = parse_level(summary.get("overall_level"))
    pressure_returncode = int(report.get("pressure_test", {}).get("returncode", -1))

    violations: List[str] = []
    if actual_score < min_score:
        violations.append(f"overall_score too low: {actual_score:.3f} < {min_score:.3f}")
    if LEVEL_RANK.get(actual_level, 0) < LEVEL_RANK.get(min_level, 0):
        violations.append(f"overall_level too low: {actual_level} < {min_level}")
    if require_pressure_pass and pressure_returncode != 0:
        violations.append(f"pressure test not passed: returncode={pressure_returncode}")

    if violations:
        print(f"[{TOOL}] FAIL: gate failed ({len(violations)} violation(s))")
        for item in violations:
            print(f"[{TOOL}] violation: {item}")
        return EXIT_AUDIT_GATE_FAIL

    if min_score > 0.0 or min_level != "low" or require_pressure_pass:
        print(
            f"[{TOOL}] PASS: score={actual_score:.3f} level={actual_level} "
            f"threshold(score>={min_score:.3f}, level>={min_level}, require_pressure={int(require_pressure_pass)})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
