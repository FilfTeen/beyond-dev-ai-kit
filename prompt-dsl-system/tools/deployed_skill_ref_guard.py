#!/usr/bin/env python3
"""Ensure every deployed skill is referenced by at least one pipeline."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Set

from skill_promotion_matrix import extract_pipeline_skill_refs, load_pipeline_texts

TOOL = "deployed_skill_ref_guard"
TOOL_VERSION = "1.0.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_registry(path: Path) -> List[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("skills.json must be a JSON array")
    return [item for item in data if isinstance(item, dict)]


def normalize_skill_names(raw: object) -> Set[str]:
    if isinstance(raw, str):
        parts = [seg.strip() for seg in raw.split(",")]
        return {seg for seg in parts if seg}
    if isinstance(raw, (list, tuple, set)):
        out: Set[str] = set()
        for item in raw:
            if isinstance(item, str):
                value = item.strip()
                if value:
                    out.add(value)
        return out
    return set()


def build_cover_map(skills: Iterable[dict]) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {}
    for item in skills:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        covers = normalize_skill_names(item.get("covers"))
        if covers:
            out[name] = covers
    return out


def expand_skill_refs(refs: Set[str], cover_map: Dict[str, Set[str]]) -> Set[str]:
    expanded = set(refs)
    queue = list(refs)
    while queue:
        current = queue.pop()
        for covered in cover_map.get(current, set()):
            if covered not in expanded:
                expanded.add(covered)
                queue.append(covered)
    for name in list(expanded):
        # Legacy compatibility: *_with_hints implies base discover skill.
        if name.endswith("_with_hints"):
            base_name = name[: -len("_with_hints")].strip()
            if base_name:
                expanded.add(base_name)
    return expanded


def run_guard(repo_root: Path) -> dict:
    registry_path = repo_root / "prompt-dsl-system/05_skill_registry/skills.json"
    pipeline_dir = repo_root / "prompt-dsl-system/04_ai_pipeline_orchestration"

    skills = load_registry(registry_path)
    pipelines = load_pipeline_texts(pipeline_dir)
    cover_map = build_cover_map(skills)
    pipeline_skill_map: Dict[str, Set[str]] = {
        name: expand_skill_refs(extract_pipeline_skill_refs(text), cover_map)
        for name, text in pipelines.items()
    }

    deployed_names = sorted(
        str(item.get("name", "")).strip()
        for item in skills
        if str(item.get("status", "")).strip() == "deployed" and str(item.get("name", "")).strip()
    )
    refs_by_skill: Dict[str, List[str]] = {}
    for skill_name in deployed_names:
        refs = sorted(
            pipeline_name for pipeline_name, refs in pipeline_skill_map.items() if skill_name in refs
        )
        refs_by_skill[skill_name] = refs

    missing = [name for name in deployed_names if not refs_by_skill.get(name)]
    passed = not missing

    return {
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "summary": {
            "passed": passed,
            "deployed_total": len(deployed_names),
            "missing_total": len(missing),
            "pipeline_total": len(pipelines),
        },
        "cover_map": {k: sorted(v) for k, v in sorted(cover_map.items())},
        "missing_deployed_skills": missing,
        "references": refs_by_skill,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate deployed skills are referenced by pipelines.")
    parser.add_argument("--repo-root", required=True, help="Repository root")
    parser.add_argument(
        "--out-json",
        default="prompt-dsl-system/tools/deployed_skill_ref_report.json",
        help="Output JSON report path",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.is_dir():
        print(f"[{TOOL}] FAIL: invalid repo root: {repo_root}")
        return 2

    report = run_guard(repo_root=repo_root)
    out_json = Path(args.out_json)
    if not out_json.is_absolute():
        out_json = repo_root / out_json
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if bool(report.get("summary", {}).get("passed", False)):
        print(f"[{TOOL}] PASS: {out_json}")
        return 0
    print(f"[{TOOL}] FAIL: {out_json}")
    for name in report.get("missing_deployed_skills", []):
        print(f"  - missing_pipeline_ref: {name}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
