#!/usr/bin/env python3
"""Natural-language router with scan-first adaptive strategy.

Design goals:
1) Avoid hard-coded specialized pipeline routing.
2) Prefer one generic adaptive pipeline for non-explicit requests.
3) Scan available pipelines for evidence and report top candidates.
4) Use specialized pipeline only when user explicitly names it.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


PIPELINE_DIR = Path("prompt-dsl-system/04_ai_pipeline_orchestration")
RUN_SH = Path("prompt-dsl-system/tools/run.sh")
GENERIC_FALLBACK_PIPELINE = "pipeline_bugfix_min_scope_with_tree.md"

_TEXT_SPLIT_RE = re.compile(r"[^a-z0-9\u4e00-\u9fff./_-]+")
_PIPELINE_PATH_RE = re.compile(
    r"(prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_[A-Za-z0-9_]+\.md|pipeline_[A-Za-z0-9_]+\.md)"
)
_MODULE_PATH_ASSIGN_RE = re.compile(
    r"(?:module[_-]?path)\s*[:=]\s*([^\s,;，。；：！？]+)",
    re.IGNORECASE,
)
_PATH_TOKEN_RE = re.compile(r"(?<!\S)(/[^,\s;，。；：！？]+|\./[^,\s;，。；：！？]+|\.\./[^,\s;，。；：！？]+)")
_KIT_SCOPE_LINE_RE = re.compile(
    r"allowed_module_root[^\n]{0,120}(?:must be|必须为)[^\n]{0,120}prompt-dsl-system",
    re.IGNORECASE,
)
_TRIM_WRAP_QUOTES = "\"'`“”‘’"
_TRIM_WRAP_BRACKETS = "()[]{}<>（）【】《》「」"
_TRAILING_PATH_PUNCT = ",;:!?，。；：！？"

_ALIASES = (
    ("达梦", "dm8"),
    ("自升级", "self upgrade"),
    ("自检", "selfcheck"),
    ("查漏补缺", "validate"),
    ("业主委员会", "ownercommittee"),
    ("业委会", "ownercommittee"),
    ("自然语言", "nl"),
)

_GENERIC_PIPELINE_NAME_HINTS = ("bugfix", "generic", "universal", "adaptive")


@dataclass(frozen=True)
class CommandRule:
    key: str
    target: str
    description: str
    groups: Tuple[Tuple[str, ...], ...]
    min_hits: int = 1
    weight: int = 6


@dataclass(frozen=True)
class PipelineProfile:
    name: str
    path: str
    tokens: Tuple[str, ...]
    title: str
    scenario_excerpt: str
    is_generic: bool
    default_module_path: Optional[str]


@dataclass(frozen=True)
class RankedPipeline:
    profile: PipelineProfile
    score: int
    matched: Tuple[str, ...]


COMMAND_RULES: Tuple[CommandRule, ...] = (
    CommandRule(
        key="self_upgrade",
        target="self-upgrade",
        description="Run kit self-upgrade workflow.",
        groups=(
            ("self upgrade", "self-upgrade", "自升级", "套件升级"),
        ),
    ),
    CommandRule(
        key="validate",
        target="validate",
        description="Validate registry/pipelines and run post-validate gates.",
        groups=(
            ("validate", "校验", "验证", "查漏补缺", "完整性"),
        ),
    ),
    CommandRule(
        key="selfcheck",
        target="selfcheck",
        description="Run kit quality scorecard.",
        groups=(
            ("selfcheck", "质量评分", "质量体检", "评分"),
        ),
    ),
    CommandRule(
        key="list",
        target="list",
        description="List active skill registry entries.",
        groups=(
            ("list", "列出", "查看"),
            ("skills", "skill list", "技能列表", "registry"),
        ),
        min_hits=2,
    ),
)


def normalize_text(text: str) -> str:
    out = text.strip().lower()
    for src, dst in _ALIASES:
        out = out.replace(src, dst)
    parts = [p for p in _TEXT_SPLIT_RE.split(out) if p]
    return " ".join(parts)


def build_token_set(text: str) -> set[str]:
    tokens = set(text.split())
    compact = text.replace(" ", "")
    if compact:
        tokens.add(compact)
    return tokens


def term_hit(term: str, norm_text: str, token_set: set[str]) -> bool:
    term_norm = normalize_text(term)
    if not term_norm:
        return False
    return term_norm in token_set or term_norm in norm_text


def has_change_signal(norm_text: str, token_set: set[str]) -> bool:
    return any(
        term_hit(term, norm_text, token_set)
        for term in (
            "修复",
            "改进",
            "优化",
            "新增",
            "实现",
            "开发",
            "重构",
            "迁移",
            "fix",
            "bugfix",
            "refactor",
            "implement",
        )
    )


def infer_module_path(goal_raw: str) -> Optional[str]:
    def sanitize_candidate(raw_candidate: str) -> str:
        candidate = raw_candidate.strip()
        if not candidate:
            return ""
        # Remove paired wrappers once or twice: "path", 'path', （path）, 【path】.
        for _ in range(2):
            if len(candidate) >= 2 and (
                candidate[0] in (_TRIM_WRAP_QUOTES + _TRIM_WRAP_BRACKETS)
                and candidate[-1] in (_TRIM_WRAP_QUOTES + _TRIM_WRAP_BRACKETS + _TRAILING_PATH_PUNCT)
            ):
                candidate = candidate.strip(_TRIM_WRAP_QUOTES + _TRIM_WRAP_BRACKETS).strip()
            else:
                break
        candidate = candidate.strip(_TRIM_WRAP_QUOTES + _TRIM_WRAP_BRACKETS).rstrip(_TRAILING_PATH_PUNCT)
        return candidate.strip()

    assign_match = _MODULE_PATH_ASSIGN_RE.search(goal_raw)
    if assign_match:
        value = sanitize_candidate(assign_match.group(1))
        if value and not value.endswith(".md"):
            return value

    for path_match in _PATH_TOKEN_RE.finditer(goal_raw):
        candidate = sanitize_candidate(path_match.group(1))
        if candidate.endswith(".md"):
            continue
        if "pipeline_" in candidate:
            continue
        return candidate
    return None


def load_pipeline_profile(path: Path, repo_root: Path) -> PipelineProfile:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    title = ""
    scenario_lines: List[str] = []
    in_scenario = False

    for line in lines[:220]:
        stripped = line.strip()
        if not title and stripped.startswith("# "):
            title = stripped[2:].strip()
        if stripped.startswith("## 适用场景") or stripped.startswith("## Scope"):
            in_scenario = True
            continue
        if in_scenario:
            if stripped.startswith("## "):
                break
            if stripped.startswith("- "):
                scenario_lines.append(stripped[2:].strip())

    scenario_excerpt = " | ".join(scenario_lines[:5])
    norm = normalize_text(f"{path.stem} {title} {scenario_excerpt}")
    token_set = build_token_set(norm)
    is_generic = any(h in path.stem.lower() for h in _GENERIC_PIPELINE_NAME_HINTS) or "通用" in title or "generic" in title.lower()
    default_module_path = "prompt-dsl-system" if _KIT_SCOPE_LINE_RE.search(raw) else None

    return PipelineProfile(
        name=path.stem,
        path=path.relative_to(repo_root).as_posix(),
        tokens=tuple(sorted(token_set)),
        title=title,
        scenario_excerpt=scenario_excerpt,
        is_generic=is_generic,
        default_module_path=default_module_path,
    )


def discover_pipelines(repo_root: Path) -> List[PipelineProfile]:
    pipeline_root = repo_root / PIPELINE_DIR
    profiles: List[PipelineProfile] = []
    for path in sorted(pipeline_root.glob("pipeline_*.md")):
        if path.is_file():
            profiles.append(load_pipeline_profile(path=path, repo_root=repo_root))
    return profiles


def score_command(goal_norm: str) -> Tuple[Optional[CommandRule], int, List[str]]:
    token_set = build_token_set(goal_norm)
    has_upgrade_signal = any(
        term_hit(term, goal_norm, token_set)
        for term in ("self upgrade", "self-upgrade", "自升级", "升级", "upgrade")
    )
    change_signal = has_change_signal(goal_norm, token_set)

    best_rule: Optional[CommandRule] = None
    best_score = -10**9
    best_hits: List[str] = []

    for rule in COMMAND_RULES:
        hits = 0
        hit_terms: List[str] = []
        for group in rule.groups:
            group_hit = False
            for term in group:
                if term_hit(term, goal_norm, token_set):
                    group_hit = True
                    hit_terms.append(term)
                    break
            if group_hit:
                hits += 1

        score = hits * rule.weight
        if hits < rule.min_hits:
            score -= (rule.min_hits - hits) * (rule.weight + 2)

        # Conflict resolver: upgrade intents should not be stolen by "校验/验证".
        if rule.key == "self_upgrade" and has_upgrade_signal:
            score += 3
        if rule.key == "validate" and has_upgrade_signal:
            score -= 3
        # For goals that include concrete change intent (fix/develop/refactor),
        # prefer adaptive pipeline routing over command-only validate.
        if rule.key == "validate" and change_signal:
            score -= 4

        if score > best_score or (score == best_score and len(hit_terms) > len(best_hits)):
            best_rule = rule
            best_score = score
            best_hits = hit_terms

    return best_rule, best_score, best_hits


def rank_pipelines(goal_norm: str, profiles: Sequence[PipelineProfile]) -> List[RankedPipeline]:
    token_set = build_token_set(goal_norm)
    change_signal = has_change_signal(goal_norm, token_set)
    ranked: List[RankedPipeline] = []

    for profile in profiles:
        matched: List[str] = []
        score = 0

        for token in token_set:
            if token in profile.tokens:
                score += 3
                matched.append(token)

        # Reward exact pipeline stem mention.
        if profile.name.lower() in goal_norm:
            score += 10

        # Stabilize generic route for change/fix development intents.
        if change_signal and profile.is_generic:
            score += 3
            matched.append("change_signal")

        # Penalize specialized pipelines when intent is not explicit.
        if not profile.is_generic:
            score -= 2

        ranked.append(
            RankedPipeline(
                profile=profile,
                score=score,
                matched=tuple(matched[:8]),
            )
        )

    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked


def detect_explicit_pipeline(goal_raw: str, profiles: Sequence[PipelineProfile]) -> Optional[PipelineProfile]:
    goal_norm = normalize_text(goal_raw)
    explicit_match = _PIPELINE_PATH_RE.search(goal_raw)
    if explicit_match:
        raw = explicit_match.group(1).strip()
        raw_name = Path(raw).stem
        for profile in profiles:
            if profile.name == raw_name:
                return profile

    # Also allow explicit mention by stem without path.
    for profile in profiles:
        if profile.name.lower() in goal_norm and "pipeline_" in goal_norm:
            return profile
    return None


def calibrate_confidence(mode: str, top_score: int, margin: int) -> float:
    if mode == "explicit_pipeline":
        return 0.92
    if mode == "command":
        base = top_score / 12.0
        if margin >= 5:
            base += 0.15
        return max(0.05, min(0.99, round(base, 2)))
    # Adaptive fallback mode.
    if top_score >= 5:
        base = 0.66
    elif top_score >= 3:
        base = 0.54
    else:
        base = 0.46
    if margin <= 1:
        base -= 0.06
    return max(0.05, min(0.99, round(base, 2)))


def choose_action(goal_raw: str, repo_root: Path) -> Dict[str, Any]:
    t0 = time.perf_counter()
    goal_norm = normalize_text(goal_raw)
    profiles = discover_pipelines(repo_root=repo_root)
    if not profiles:
        raise RuntimeError(f"no pipelines found under {PIPELINE_DIR.as_posix()}")

    ranked_pipelines = rank_pipelines(goal_norm=goal_norm, profiles=profiles)
    top_pipeline = ranked_pipelines[0]
    second_pipeline = ranked_pipelines[1] if len(ranked_pipelines) > 1 else None
    pipeline_margin = top_pipeline.score - (second_pipeline.score if second_pipeline else 0)

    cmd_rule, cmd_score, cmd_hits = score_command(goal_norm=goal_norm)
    explicit_profile = detect_explicit_pipeline(goal_raw=goal_raw, profiles=profiles)
    selected_profile: Optional[PipelineProfile] = None

    # Explicit pipeline path/name always takes precedence over generic command terms.
    if explicit_profile is not None:
        selected_profile = explicit_profile
        mode = "explicit_pipeline"
        selected_key = f"pipeline:{explicit_profile.name}"
        action_kind = "pipeline"
        target = explicit_profile.path
        description = f"Explicit pipeline requested: {explicit_profile.title or explicit_profile.name}"
        hits = [explicit_profile.name]
        confidence = calibrate_confidence(mode=mode, top_score=10, margin=10)
        ambiguous = False
    elif cmd_rule is not None and cmd_score >= 6:
        mode = "command"
        selected_key = cmd_rule.key
        action_kind = "command"
        target = cmd_rule.target
        description = cmd_rule.description
        hits = cmd_hits
        confidence = calibrate_confidence(mode=mode, top_score=cmd_score, margin=cmd_score - top_pipeline.score)
        ambiguous = cmd_score - top_pipeline.score <= 1 and cmd_score < 10
    else:
        mode = "adaptive_generic_fallback"
        fallback = next((p for p in profiles if p.name == Path(GENERIC_FALLBACK_PIPELINE).stem), None)
        selected = fallback if fallback is not None else top_pipeline.profile
        selected_profile = selected
        selected_key = "adaptive_pipeline"
        action_kind = "pipeline"
        target = selected.path
        description = "Adaptive scan-first fallback to generic pipeline (specialized pipeline disabled by default)."
        hits = list(top_pipeline.matched)
        confidence = calibrate_confidence(mode=mode, top_score=top_pipeline.score, margin=pipeline_margin)
        ambiguous = top_pipeline.score < 2

    routing_ms = round((time.perf_counter() - t0) * 1000.0, 3)
    return {
        "goal": goal_raw,
        "goal_normalized": goal_norm,
        "selected": {
            "key": selected_key,
            "action_kind": action_kind,
            "target": target,
            "description": description,
            "confidence": confidence,
            "ambiguous": ambiguous,
            "keyword_hits": hits,
            "selection_mode": mode,
            "default_module_path": selected_profile.default_module_path if selected_profile else None,
        },
        "scan_summary": {
            "pipelines_scanned": len(profiles),
            "top_pipeline_candidates": [
                {
                    "name": item.profile.name,
                    "path": item.profile.path,
                    "score": item.score,
                    "matched": list(item.matched),
                    "is_generic": item.profile.is_generic,
                    "default_module_path": item.profile.default_module_path,
                }
                for item in ranked_pipelines[:5]
            ],
        },
        "routing_time_ms": routing_ms,
    }


def build_action_command(
    repo_root: Path,
    action_kind: str,
    target: str,
    module_path: Optional[str],
) -> Tuple[List[str], str]:
    script_path = str((repo_root / RUN_SH).resolve())
    if action_kind == "pipeline":
        cmd = [script_path, "run", "--repo-root", str(repo_root.resolve()), "--pipeline", target]
        pretty = ["./prompt-dsl-system/tools/run.sh", "run", "-r", "."]
        if module_path:
            cmd.extend(["--module-path", module_path])
            pretty.extend(["-m", module_path])
        else:
            pretty.extend(["-m", "<MODULE_PATH>"])
        pretty.extend(["--pipeline", target])
        return cmd, " ".join(pretty)

    cmd = [script_path, target, "--repo-root", str(repo_root.resolve())]
    pretty = ["./prompt-dsl-system/tools/run.sh", target, "-r", "."]
    if module_path:
        cmd.extend(["--module-path", module_path])
        pretty.extend(["-m", module_path])
    return cmd, " ".join(pretty)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan-first adaptive NL router.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--module-path", default="", help="Optional module path override.")
    parser.add_argument("--goal", default="", help="Natural-language goal text.")
    parser.add_argument("--execute", action="store_true", help="Execute routed action.")
    parser.add_argument("--force-execute", action="store_true", help="Bypass confidence/ambiguity gate.")
    parser.add_argument("--min-confidence", default="0.50", help="Execution confidence threshold.")
    parser.add_argument("goal_words", nargs="*", help="Goal words when --goal is omitted.")
    return parser.parse_args(argv)


def parse_min_confidence(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError:
        return 0.50
    return max(0.01, min(0.99, value))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def collect_git_changed_paths(repo_root: Path) -> List[str]:
    cmd = [
        "git",
        "-C",
        str(repo_root),
        "status",
        "--porcelain",
        "--untracked-files=all",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    changed: List[str] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        payload = line[3:].strip()
        if not payload:
            continue
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1].strip()
        changed.append(payload)
    return changed


def detect_scope_conflicts(repo_root: Path, module_path: str) -> Dict[str, Any]:
    module_abs = Path(module_path)
    if not module_abs.is_absolute():
        module_abs = (repo_root / module_abs).resolve()
    else:
        module_abs = module_abs.resolve()
    kit_abs = (repo_root / "prompt-dsl-system").resolve()

    changed = collect_git_changed_paths(repo_root=repo_root)
    conflicts: List[str] = []
    for rel in changed:
        candidate = (repo_root / rel).resolve()
        if _is_within(candidate, module_abs) or _is_within(candidate, kit_abs):
            continue
        conflicts.append(rel)
    return {
        "checked": True,
        "changed_file_count": len(changed),
        "out_of_scope_count": len(conflicts),
        "out_of_scope_samples": conflicts[:8],
    }


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    if not repo_root.exists():
        print(f"[intent][ERROR] repo root not found: {repo_root}", file=sys.stderr)
        return 2

    goal = args.goal.strip() or " ".join(args.goal_words).strip()
    if not goal:
        print("[intent][ERROR] missing goal; use --goal \"...\"", file=sys.stderr)
        return 2

    routed = choose_action(goal_raw=goal, repo_root=repo_root)
    selected = routed["selected"]
    action_kind = str(selected["action_kind"])
    target = str(selected["target"])

    inferred_module_path = infer_module_path(goal_raw=goal)
    selected_default_module_path = None
    if action_kind == "pipeline":
        selected_default_module_path = str(selected.get("default_module_path") or "").strip() or None

    module_path = (args.module_path or "").strip() or inferred_module_path or selected_default_module_path or None
    cmd, pretty_cmd = build_action_command(
        repo_root=repo_root,
        action_kind=action_kind,
        target=target,
        module_path=module_path,
    )

    routed["run_command"] = pretty_cmd
    routed["module_path_source"] = (
        "cli"
        if (args.module_path or "").strip()
        else "goal"
        if inferred_module_path
        else "selected_default"
        if selected_default_module_path
        else "missing"
    )

    execution_ready = action_kind != "pipeline" or bool(module_path)
    routed["execution_ready"] = execution_ready
    if not execution_ready:
        routed["required_additional_information"] = ["module_path"]

    min_conf = parse_min_confidence(args.min_confidence)
    confidence = float(selected.get("confidence", 0.0))
    ambiguous = bool(selected.get("ambiguous", False))
    can_auto_execute = execution_ready and (confidence >= min_conf) and (not ambiguous)
    blockers: List[str] = []

    if args.execute and action_kind == "pipeline" and module_path:
        scope_check = detect_scope_conflicts(repo_root=repo_root, module_path=module_path)
        routed["workspace_scope_check"] = scope_check
        if scope_check.get("out_of_scope_count", 0) > 0:
            blockers.append("workspace_out_of_scope_changes")
            can_auto_execute = False
    else:
        routed["workspace_scope_check"] = {
            "checked": False,
            "reason": "only checked for pipeline execute with resolved module_path",
        }

    if blockers:
        routed["execution_blockers"] = blockers
    routed["can_auto_execute"] = can_auto_execute
    routed["execution_policy"] = {
        "min_confidence": min_conf,
        "force_execute": bool(args.force_execute),
    }

    print(json.dumps(routed, ensure_ascii=False, indent=2))

    if not args.execute:
        return 0
    if not execution_ready:
        print("[intent][ERROR] execute requires module path; provide --module-path", file=sys.stderr)
        return 2
    if not args.force_execute and not can_auto_execute:
        print("[intent][ERROR] blocked execute due to low confidence or ambiguity", file=sys.stderr)
        return 2

    print(f"[intent] executing: {pretty_cmd}")
    proc = subprocess.run(cmd, cwd=str(repo_root))
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
