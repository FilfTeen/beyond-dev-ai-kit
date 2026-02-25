#!/usr/bin/env python3
"""Generate promotion readiness matrix for staging skills."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

TOOL = "skill_promotion_matrix"
TOOL_VERSION = "1.0.0"
YAML_BLOCK_RE = re.compile(r"```(?:yaml|yml)\n(.*?)```", re.IGNORECASE | re.DOTALL)
SKILL_LINE_RE = re.compile(r"^\s*skill\s*:\s*([^\n#]+?)\s*$", re.IGNORECASE | re.MULTILINE)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_registry(path: Path) -> List[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("skills.json must be a JSON array")
    return [item for item in data if isinstance(item, dict)]


def load_pipeline_texts(pipeline_dir: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for path in sorted(pipeline_dir.glob("pipeline_*.md")):
        if path.is_file():
            out[path.name] = path.read_text(encoding="utf-8", errors="ignore")
    return out


def _strip_quotes(text: str) -> str:
    value = str(text or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def extract_pipeline_skill_refs(pipeline_text: str) -> set[str]:
    refs: set[str] = set()
    for block in YAML_BLOCK_RE.findall(pipeline_text or ""):
        for raw in SKILL_LINE_RE.findall(block):
            candidate = _strip_quotes(raw.strip())
            if candidate:
                refs.add(candidate)
    return refs


def check_yaml_markers(skill_text: str) -> Dict[str, bool]:
    markers = {
        "has_name": "name:" in skill_text,
        "has_description": "description:" in skill_text,
        "has_parameters": "parameters:" in skill_text,
        "has_prompt_template": "prompt_template:" in skill_text,
        "has_output_contract": "output_contract:" in skill_text,
        "has_examples": "examples:" in skill_text,
    }
    return markers


def score_checks(checks: Dict[str, bool]) -> float:
    if not checks:
        return 0.0
    ok = sum(1 for v in checks.values() if v)
    return round(ok / len(checks), 3)


def render_markdown(report: dict) -> str:
    lines: List[str] = []
    summary = report.get("summary", {})
    lines.append("# Skill Promotion Matrix")
    lines.append("")
    lines.append(f"- generated_at: `{report.get('generated_at', '-')}`")
    lines.append(f"- repo_root: `{report.get('repo_root', '-')}`")
    lines.append(f"- staging_total: `{summary.get('staging_total', 0)}`")
    lines.append(f"- ready_total: `{summary.get('ready_total', 0)}`")
    lines.append(f"- pending_total: `{summary.get('pending_total', 0)}`")
    lines.append("")
    lines.append("| Skill | Domain | Score | Ready | Pipeline Refs | Missing |")
    lines.append("|---|---|---:|---|---:|---|")
    for item in report.get("items", []):
        missing = ", ".join(item.get("missing", [])) or "-"
        lines.append(
            f"| {item.get('name', '-')} | {item.get('domain', '-')} | {item.get('readiness_score', 0)} | "
            f"{'yes' if item.get('ready') else 'no'} | {item.get('pipeline_ref_count', 0)} | {missing} |"
        )
    lines.append("")
    lines.append("## Suggested Order")
    lines.append("")
    for idx, item in enumerate(report.get("promotion_order", []), start=1):
        lines.append(f"{idx}. `{item}`")
    if not report.get("promotion_order"):
        lines.append("1. none")
    return "\n".join(lines) + "\n"


def build_report(repo_root: Path) -> dict:
    registry_path = repo_root / "prompt-dsl-system/05_skill_registry/skills.json"
    pipeline_dir = repo_root / "prompt-dsl-system/04_ai_pipeline_orchestration"

    skills = load_registry(registry_path)
    pipelines = load_pipeline_texts(pipeline_dir)
    pipeline_skill_map: Dict[str, set[str]] = {
        pipeline_name: extract_pipeline_skill_refs(pipeline_text)
        for pipeline_name, pipeline_text in pipelines.items()
    }

    items = []
    for skill in skills:
        if skill.get("status") != "staging":
            continue
        name = str(skill.get("name", "")).strip()
        path_rel = str(skill.get("path", "")).strip()
        domain = str(skill.get("domain", "")).strip() or "unknown"
        skill_path = (repo_root / path_rel).resolve() if path_rel else None

        path_exists = bool(skill_path and skill_path.is_file())
        text = skill_path.read_text(encoding="utf-8", errors="ignore") if path_exists else ""
        marker_checks = check_yaml_markers(text) if path_exists else {}
        marker_score = score_checks(marker_checks)

        pipeline_refs = []
        if name:
            for pipeline_name, skill_refs in pipeline_skill_map.items():
                if name in skill_refs:
                    pipeline_refs.append(pipeline_name)

        checks: Dict[str, bool] = {
            "path_exists": path_exists,
            "yaml_markers_ok": bool(path_exists and marker_score >= 1.0),
            "referenced_by_pipeline": bool(pipeline_refs),
        }
        readiness_score = score_checks(checks)
        ready = readiness_score >= 1.0
        missing = [k for k, v in checks.items() if not v]
        if path_exists and marker_score < 1.0:
            missing_markers = [k for k, v in marker_checks.items() if not v]
            if missing_markers:
                missing.append("yaml:" + ",".join(missing_markers))

        items.append(
            {
                "name": name,
                "domain": domain,
                "status": "staging",
                "path": path_rel,
                "readiness_score": readiness_score,
                "ready": ready,
                "checks": checks,
                "missing": missing,
                "pipeline_refs": pipeline_refs,
                "pipeline_ref_count": len(pipeline_refs),
            }
        )

    items.sort(key=lambda item: (-float(item["readiness_score"]), item["name"]))
    ready_items = [item["name"] for item in items if item.get("ready")]
    pending_items = [item["name"] for item in items if not item.get("ready")]

    domain_dist = Counter(item.get("domain", "unknown") for item in items)

    return {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "summary": {
            "staging_total": len(items),
            "ready_total": len(ready_items),
            "pending_total": len(pending_items),
            "domain_distribution": dict(sorted(domain_dist.items())),
            "pipeline_total": len(pipelines),
        },
        "promotion_order": ready_items + pending_items,
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate promotion matrix for staging skills.")
    parser.add_argument("--repo-root", required=True, help="Repository root")
    parser.add_argument(
        "--out-json",
        default="prompt-dsl-system/tools/skill_promotion_matrix.json",
        help="Output JSON report path",
    )
    parser.add_argument(
        "--out-md",
        default="prompt-dsl-system/tools/skill_promotion_matrix.md",
        help="Output Markdown report path",
    )
    parser.add_argument(
        "--fail-on-pending",
        action="store_true",
        help="Exit non-zero when pending staging skills exist",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[{TOOL}] FAIL: invalid repo root: {repo_root}")
        return 2

    report = build_report(repo_root=repo_root)
    md = render_markdown(report)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not out_json.is_absolute():
        out_json = repo_root / out_json
    if not out_md.is_absolute():
        out_md = repo_root / out_md
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(md, encoding="utf-8")

    pending_total = int(report.get("summary", {}).get("pending_total", 0))
    print(f"[{TOOL}] json={out_json}")
    print(f"[{TOOL}] md={out_md}")
    print(
        f"[{TOOL}] staging_total={report['summary']['staging_total']} "
        f"ready_total={report['summary']['ready_total']} pending_total={pending_total}"
    )
    if args.fail_on_pending and pending_total > 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
