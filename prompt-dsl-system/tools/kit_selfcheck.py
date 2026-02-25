#!/usr/bin/env python3
"""Kit self-check scorecard for beyond-dev-ai-kit.

Evaluates toolkit quality dimensions and emits JSON/Markdown reports.
Standard-library only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

TOOL_VERSION = "1.0.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def quote_machine_value(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def build_machine_json(path_value: str, report: dict) -> str:
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    repo_snapshot = report.get("repo_snapshot", {}) if isinstance(report, dict) else {}
    payload = {
        "path": str(path_value),
        "command": "selfcheck",
        "tool": "kit_selfcheck",
        "tool_version": TOOL_VERSION,
        "generated_at": str(report.get("generated_at", now_iso())),
        "overall_score": float(summary.get("overall_score", 0.0)),
        "overall_level": str(summary.get("overall_level", "low")),
        "dimension_count": int(summary.get("dimension_count", 0)),
        "git_head": str(repo_snapshot.get("git_head", "")),
        "git_head_available": bool(repo_snapshot.get("git_head_available", False)),
        "git_dirty": bool(repo_snapshot.get("git_dirty", False)),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return encoded.replace("'", "\\u0027")


def score_to_level(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"


def check_paths(repo_root: Path, required_paths: List[str]) -> Tuple[float, List[dict], List[str]]:
    checks: List[dict] = []
    missing: List[str] = []
    found_count = 0

    for rel in required_paths:
        path = repo_root / rel
        exists = path.exists()
        checks.append({"path": rel, "exists": bool(exists)})
        if exists:
            found_count += 1
        else:
            missing.append(rel)

    score = (found_count / len(required_paths)) if required_paths else 1.0
    return score, checks, missing


def load_json_file(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def read_text_file(repo_root: Path, rel_path: str) -> str:
    path = repo_root / rel_path
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def list_pipelines(repo_root: Path) -> List[str]:
    pipeline_root = repo_root / "prompt-dsl-system" / "04_ai_pipeline_orchestration"
    if not pipeline_root.is_dir():
        return []
    return sorted(p.name for p in pipeline_root.glob("pipeline_*.md"))


def count_registry_skills(repo_root: Path) -> int:
    path = repo_root / "prompt-dsl-system" / "05_skill_registry" / "skills.json"
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(data, list):
        return 0
    return len(data)


def _run_git(repo_root: Path, args: List[str]) -> Tuple[bool, str]:
    cmd = ["git", "-C", str(repo_root)] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError:
        return False, ""
    if proc.returncode != 0:
        return False, ""
    return True, str(proc.stdout or "").strip()


def collect_repo_snapshot(repo_root: Path) -> dict:
    head_ok, head = _run_git(repo_root, ["rev-parse", "--verify", "HEAD"])
    branch_ok, branch = _run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    status_ok, status = _run_git(repo_root, ["status", "--porcelain"])
    status_lines = [line for line in status.splitlines() if line.strip()] if status_ok else []

    return {
        "git_head": head if head_ok else "",
        "git_head_available": bool(head_ok and head),
        "git_branch": branch if branch_ok else "",
        "git_dirty": bool(status_lines) if status_ok else False,
        "git_status_entries": len(status_lines),
        "git_status_available": bool(status_ok),
    }


def run_intent_probe(repo_root: Path, goal: str) -> dict:
    router = repo_root / "prompt-dsl-system" / "tools" / "intent_router.py"
    if not router.is_file():
        return {
            "goal": goal,
            "passed": False,
            "reason": "router_missing",
            "target": "",
            "selection_mode": "",
        }

    cmd = [sys.executable, str(router), "--repo-root", str(repo_root), "--goal", goal]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        return {
            "goal": goal,
            "passed": False,
            "reason": "router_exec_error",
            "target": "",
            "selection_mode": "",
        }
    if proc.returncode != 0:
        return {
            "goal": goal,
            "passed": False,
            "reason": f"router_exit_{proc.returncode}",
            "target": "",
            "selection_mode": "",
        }

    try:
        routed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "goal": goal,
            "passed": False,
            "reason": "router_output_parse_error",
            "target": "",
            "selection_mode": "",
        }
    selected = routed.get("selected", {}) if isinstance(routed.get("selected"), dict) else {}
    return {
        "goal": goal,
        "passed": False,
        "reason": "",
        "target": str(selected.get("target", "")),
        "selection_mode": str(selected.get("selection_mode", "")),
    }


def score_route_probes(repo_root: Path) -> Tuple[float, List[dict]]:
    probes = [
        {
            "goal": "为 notice 模块生成单元测试并输出覆盖率报告",
            "expect_target_suffix": "pipeline_test_gen.md",
            "expect_mode": "specialized_pipeline",
        },
        {
            "goal": "对 ownercommittee 模块做安全审计并输出风险报告",
            "expect_target_suffix": "pipeline_security_audit.md",
            "expect_mode": "specialized_pipeline",
        },
        {
            "goal": "基于最新创建提示词改进 beyond-dev-ai-kit 的 prompt/DSL/skill/pipeline 套件并落地",
            "expect_target_suffix": "pipeline_kit_self_upgrade.md",
            "expect_mode": "kit_self_upgrade_priority",
        },
    ]
    results: List[dict] = []
    passed = 0
    for item in probes:
        result = run_intent_probe(repo_root=repo_root, goal=str(item["goal"]))
        target_ok = result.get("target", "").endswith(str(item["expect_target_suffix"]))
        mode_ok = result.get("selection_mode", "") == str(item["expect_mode"])
        ok = bool(target_ok and mode_ok)
        if ok:
            passed += 1
        results.append(
            {
                **item,
                "target": result.get("target", ""),
                "selection_mode": result.get("selection_mode", ""),
                "passed": ok,
                "reason": result.get("reason", ""),
            }
        )
    score = (passed / len(probes)) if probes else 1.0
    return score, results


def run_selfcheck(repo_root: Path) -> dict:
    dimensions: Dict[str, dict] = {}

    required_map = {
        "generality": [
            "prompt-dsl-system/00_conventions/PROJECT_PROFILE_SPEC.md",
            "prompt-dsl-system/00_conventions/MODULE_PROFILE_SPEC.md",
            "prompt-dsl-system/00_conventions/PROJECT_TECH_STACK_SPEC.md",
            "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_project_bootstrap.md",
            "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_module_migration.md",
        ],
        "completeness": [
            "prompt-dsl-system/00_conventions/FACT_BASELINE.md",
            "prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md",
            "prompt-dsl-system/00_conventions/SKILL_SPEC.md",
            "prompt-dsl-system/05_skill_registry/skills.json",
            "prompt-dsl-system/04_ai_pipeline_orchestration/README.md",
        ],
        "robustness": [
            "prompt-dsl-system/tools/run.sh",
            "prompt-dsl-system/tools/ops_guard.py",
            "prompt-dsl-system/tools/pipeline_contract_lint.py",
            "prompt-dsl-system/tools/skill_template_audit.py",
            "prompt-dsl-system/tools/golden_path_regression.sh",
            "prompt-dsl-system/tools/baseline_provenance_guard.py",
            "prompt-dsl-system/tools/gate_mutation_guard.py",
            "prompt-dsl-system/00_conventions/ROLLBACK_INSTRUCTIONS.md",
        ],
        "efficiency": [
            "prompt-dsl-system/tools/scan_graph.py",
            "prompt-dsl-system/tools/module_profile_scanner.py",
            "prompt-dsl-system/tools/auto_module_discover.py",
            "prompt-dsl-system/tools/cross_project_structure_diff.py",
            "prompt-dsl-system/tools/calibration_engine.py",
            "prompt-dsl-system/tools/performance_budget_guard.py",
        ],
        "extensibility": [
            "prompt-dsl-system/05_skill_registry/templates/skill_template/skill.yaml.template",
            "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_skill_creator.md",
            "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_skill_promote.md",
            "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_project_stack_bootstrap.md",
            "prompt-dsl-system/00_conventions/KIT_QUALITY_MODEL.md",
        ],
        "security_governance": [
            "prompt-dsl-system/00_conventions/HONGZHI_COMPANY_CONSTITUTION.md",
            "prompt-dsl-system/tools/path_diff_guard.py",
            "prompt-dsl-system/tools/hongzhi_plugin.py",
            "prompt-dsl-system/tools/PLUGIN_RUNNER.md",
            "prompt-dsl-system/tools/policy.yaml",
            "prompt-dsl-system/tools/pipeline_trust_coverage_guard.py",
            "prompt-dsl-system/tools/baseline_provenance_guard.py",
        ],
        "kit_mainline_focus": [
            "prompt-dsl-system/00_conventions/HONGZHI_COMPANY_CONSTITUTION.md",
            "prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md",
            "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_project_stack_bootstrap.md",
            "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_requirement_to_prototype.md",
        ],
        "agent_active_ops": [
            "AGENTS.md",
            "AGENTS.zh-CN.md",
            "prompt-dsl-system/tools/run.sh",
            "prompt-dsl-system/tools/intent_router.py",
            "prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md",
            "prompt-dsl-system/05_skill_registry/skills/universal/skill_hongzhi_universal_ops.yaml",
            "prompt-dsl-system/tools/loop_detector.py",
            "prompt-dsl-system/tools/risk_gate.py",
            "prompt-dsl-system/tools/performance_budget_guard.py",
            "prompt-dsl-system/tools/tests/intent_router/intent_router_pressure.py",
        ],
    }

    recommendations: List[str] = []

    for name, required in required_map.items():
        score, checks, missing = check_paths(repo_root, required)
        level = score_to_level(score)
        dimensions[name] = {
            "score": round(score, 3),
            "level": level,
            "required_count": len(required),
            "found_count": int(round(score * len(required))),
            "checks": checks,
            "missing": missing,
        }
        if missing:
            recommendations.append(f"{name}: add missing artifacts ({len(missing)}).")

    pipeline_names = list_pipelines(repo_root)
    skill_count = count_registry_skills(repo_root)

    pipeline_score = min(1.0, len(pipeline_names) / 12.0)
    skill_score = min(1.0, skill_count / 6.0)

    completeness_dim = dimensions.get("completeness", {})
    base_completeness_score = float(completeness_dim.get("score", 0.0))
    adjusted_completeness = (base_completeness_score + pipeline_score + skill_score) / 3.0
    completeness_dim["score"] = round(adjusted_completeness, 3)
    completeness_dim["level"] = score_to_level(adjusted_completeness)
    completeness_dim["pipeline_count"] = len(pipeline_names)
    completeness_dim["skill_count"] = skill_count
    completeness_dim["pipelines"] = pipeline_names
    dimensions["completeness"] = completeness_dim

    if len(pipeline_names) < 10:
        recommendations.append("completeness: pipeline coverage is low (<10).")
    if skill_count < 5:
        recommendations.append("completeness: active skill count is low (<5).")

    constitution_text = (repo_root / "prompt-dsl-system/00_conventions/HONGZHI_COMPANY_CONSTITUTION.md").read_text(encoding="utf-8", errors="ignore") if (repo_root / "prompt-dsl-system/00_conventions/HONGZHI_COMPANY_CONSTITUTION.md").exists() else ""

    if "Rule 24 - Kit Mainline First" not in constitution_text:
        dimensions["kit_mainline_focus"]["score"] = round(dimensions["kit_mainline_focus"]["score"] * 0.6, 3)
        dimensions["kit_mainline_focus"]["level"] = score_to_level(dimensions["kit_mainline_focus"]["score"])
        recommendations.append("kit_mainline_focus: add Rule 24 enforcement in constitution.")

    agent_dim = dimensions.get("agent_active_ops", {})
    if isinstance(agent_dim, dict):
        signal_rules = [
            ("prompt-dsl-system/tools/intent_router.py", "detect_kit_self_upgrade_intent", "router_has_kit_intent_detector"),
            ("prompt-dsl-system/tools/intent_router.py", "can_auto_execute", "router_has_auto_execute_gate"),
            ("prompt-dsl-system/tools/run.sh", "[ \"$subcommand\" = \"intent\" ]", "run_sh_has_intent_entry"),
            ("prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md", "A0_authority_alignment.md", "pipeline_has_authority_alignment_step"),
            ("prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md", "A3_authority_sync_log.md", "pipeline_has_authority_sync_acceptance"),
            ("AGENTS.md", "pipeline_kit_self_upgrade.md", "agents_rule_mentions_kit_upgrade_pipeline"),
            ("prompt-dsl-system/tools/tests/intent_router/intent_router_pressure.py", "concurrent-calls", "pressure_test_has_concurrency_control"),
        ]
        signal_checks: List[dict] = []
        signal_found = 0
        for rel_path, marker, name in signal_rules:
            text = read_text_file(repo_root, rel_path)
            found = marker in text
            signal_checks.append(
                {
                    "name": name,
                    "path": rel_path,
                    "marker": marker,
                    "found": bool(found),
                }
            )
            if found:
                signal_found += 1

        signal_score = (signal_found / len(signal_rules)) if signal_rules else 1.0
        route_probe_score, route_probes = score_route_probes(repo_root=repo_root)
        base_score = float(agent_dim.get("score", 0.0))
        adjusted_agent_score = (base_score * 0.45) + (signal_score * 0.30) + (route_probe_score * 0.25)
        agent_dim["signal_checks"] = signal_checks
        agent_dim["signal_found_count"] = signal_found
        agent_dim["signal_count"] = len(signal_rules)
        agent_dim["route_probe_score"] = round(route_probe_score, 3)
        agent_dim["route_probes"] = route_probes
        agent_dim["score"] = round(adjusted_agent_score, 3)
        agent_dim["level"] = score_to_level(adjusted_agent_score)
        dimensions["agent_active_ops"] = agent_dim
        if signal_found < len(signal_rules):
            recommendations.append(
                "agent_active_ops: strengthen proactive-sensing/invocation links in router/pipeline/tests."
            )
        if route_probe_score < 1.0:
            recommendations.append("agent_active_ops: route probes failed for specialized/company intents.")

    dim_scores = [float(v.get("score", 0.0)) for v in dimensions.values()]
    overall_score = (sum(dim_scores) / len(dim_scores)) if dim_scores else 0.0
    overall_level = score_to_level(overall_score)

    if overall_level == "low":
        recommendations.append("overall: prioritize robustness and governance artifacts first.")
    elif overall_level == "medium":
        recommendations.append("overall: address missing artifacts to reach high band.")

    report = {
        "tool": "kit_selfcheck",
        "tool_version": TOOL_VERSION,
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "repo_snapshot": collect_repo_snapshot(repo_root),
        "summary": {
            "overall_score": round(overall_score, 3),
            "overall_level": overall_level,
            "dimension_count": len(dimensions),
        },
        "dimensions": dimensions,
        "recommendations": recommendations,
    }
    return report


def render_markdown(report: dict) -> str:
    summary = report.get("summary", {})
    dimensions = report.get("dimensions", {})
    recommendations = report.get("recommendations", [])

    lines: List[str] = []
    lines.append("# Kit Selfcheck Report")
    lines.append("")
    lines.append(f"- generated_at: `{report.get('generated_at', '-')}`")
    lines.append(f"- repo_root: `{report.get('repo_root', '-')}`")
    repo_snapshot = report.get("repo_snapshot", {})
    if isinstance(repo_snapshot, dict):
        lines.append(f"- git_head: `{repo_snapshot.get('git_head', '-')}`")
        lines.append(f"- git_branch: `{repo_snapshot.get('git_branch', '-')}`")
        lines.append(f"- git_dirty: `{repo_snapshot.get('git_dirty', False)}`")
    else:
        lines.append("- git_head: `-`")
        lines.append("- git_branch: `-`")
        lines.append("- git_dirty: `-`")
    lines.append(f"- overall_score: `{summary.get('overall_score', 0)}`")
    lines.append(f"- overall_level: `{summary.get('overall_level', '-')}`")
    lines.append("")
    lines.append("## Dimension Scores")
    lines.append("")
    lines.append("| Dimension | Score | Level | Missing |")
    lines.append("|---|---:|---|---:|")

    for name in sorted(dimensions.keys()):
        item = dimensions[name]
        lines.append(
            f"| {name} | {item.get('score', 0)} | {item.get('level', '-')} | {len(item.get('missing', []))} |"
        )

    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    if recommendations:
        for rec in recommendations:
            lines.append(f"- {rec}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Missing Details")
    lines.append("")
    for name in sorted(dimensions.keys()):
        missing = dimensions[name].get("missing", [])
        lines.append(f"### {name}")
        if missing:
            for path in missing:
                lines.append(f"- `{path}`")
        else:
            lines.append("- none")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run kit quality self-check and emit scorecard")
    parser.add_argument("--repo-root", required=True, help="Toolkit repository root")
    parser.add_argument(
        "--out-json",
        default="prompt-dsl-system/tools/kit_selfcheck_report.json",
        help="Output JSON report path (repo-relative unless absolute)",
    )
    parser.add_argument(
        "--out-md",
        default="prompt-dsl-system/tools/kit_selfcheck_report.md",
        help="Output Markdown report path (repo-relative unless absolute)",
    )
    parser.add_argument("--read-only", action="store_true", help="Print JSON to stdout and do not write files")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[kit_selfcheck] FAIL: invalid repo-root: {repo_root}")
        return 2

    report = run_selfcheck(repo_root)
    md = render_markdown(report)

    if args.read_only:
        machine_path = "-"
        machine_json = build_machine_json(machine_path, report)
        print(
            f"KIT_CAPS {machine_path} path={quote_machine_value(machine_path)} "
            f"json='{machine_json}' tool_version={TOOL_VERSION}"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not out_json.is_absolute():
        out_json = repo_root / out_json
    if not out_md.is_absolute():
        out_md = repo_root / out_md

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(md + "\n", encoding="utf-8")

    machine_path = str(out_json)
    machine_json = build_machine_json(machine_path, report)
    print(
        f"KIT_CAPS {machine_path} path={quote_machine_value(machine_path)} "
        f"json='{machine_json}' tool_version={TOOL_VERSION}"
    )
    print(f"[kit_selfcheck] json: {out_json}")
    print(f"[kit_selfcheck] md: {out_md}")
    print(
        f"[kit_selfcheck] overall_score={report['summary']['overall_score']} level={report['summary']['overall_level']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
