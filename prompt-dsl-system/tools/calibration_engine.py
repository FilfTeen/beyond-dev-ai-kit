#!/usr/bin/env python3
"""Calibration engine for discover confidence and human-hint suggestions.

Round20 goals:
- Provide machine-readable confidence and explanation fields.
- Produce workspace-only calibration artifacts.
- Never write into target repo root.

Standard-library only (Python 3.9+).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

CALIBRATION_VERSION = "1.0.0"

REASON_AMBIGUITY_RATIO_HIGH_NO_HINTS = "AMBIGUITY_RATIO_HIGH_NO_HINTS"
REASON_TOP2_RATIO_AMBIGUOUS = "TOP2_SCORE_RATIO_AMBIGUOUS"
REASON_CONTROLLER_NO_ENDPOINT = "CONTROLLER_WITHOUT_ENDPOINTS"
REASON_CONFIDENCE_BELOW_MIN = "CONFIDENCE_BELOW_MIN"
REASON_NO_MODULE_CANDIDATE = "NO_MODULE_CANDIDATES"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _uniq_keep_order(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        normalized = str(item or "").strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _parse_simple_scalar(value: str) -> Any:
    raw = value.strip()
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1]
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        return raw[1:-1]
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        try:
            return float(raw)
        except ValueError:
            return raw
    return raw


def _load_candidates_from_auto_discover(workspace: Path) -> List[dict]:
    auto_path = workspace / "discover" / "auto_discover.yaml"
    if not auto_path.is_file():
        return []

    candidates: List[dict] = []
    current: Optional[dict] = None
    for line in auto_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if stripped.startswith("- module_key:"):
            if current:
                candidates.append(current)
            value = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            current = {"module_key": value}
            continue
        if not current:
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        if key in {
            "package_prefix",
            "file_count",
            "controller_count",
            "service_count",
            "repository_count",
            "score",
            "confidence",
        }:
            current[key] = _parse_simple_scalar(value)

    if current:
        candidates.append(current)
    return candidates


def _load_structure_signals(workspace: Path) -> Dict[str, Any]:
    discover_dir = workspace / "discover"
    signal: Dict[str, Any] = {
        "controller_count": 0,
        "service_count": 0,
        "repository_count": 0,
        "template_count": 0,
        "endpoint_count": 0,
        "endpoint_paths": [],
        "templates": [],
        "modules": {},
    }
    if not discover_dir.is_dir():
        return signal

    for struct_path in sorted(discover_dir.glob("*.structure.yaml")):
        module_key = struct_path.stem.replace(".structure", "")
        lines = struct_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        in_summary = False
        in_endpoints = False
        in_templates = False
        module_metrics = {
            "controller_count": 0,
            "service_count": 0,
            "repository_count": 0,
            "template_count": 0,
            "endpoint_count": 0,
            "endpoint_paths": [],
            "templates": [],
        }

        for raw in lines:
            s = raw.strip()
            if s == "structure_summary:":
                in_summary = True
                in_endpoints = False
                in_templates = False
                continue
            if s == "api_endpoints:":
                in_summary = False
                in_endpoints = True
                in_templates = False
                continue
            if s == "templates:":
                in_summary = False
                in_endpoints = False
                in_templates = True
                continue
            if not s:
                continue

            if in_summary and ":" in s:
                key, value = s.split(":", 1)
                key = key.strip()
                value = value.strip()
                if key in module_metrics:
                    module_metrics[key] = _to_int(_parse_simple_scalar(value), 0)
                continue

            if in_endpoints and s.startswith("- path:"):
                endpoint_path = s.split(":", 1)[1].strip().strip('"').strip("'")
                if endpoint_path:
                    module_metrics["endpoint_paths"].append(endpoint_path)
                continue

            if in_templates and s.startswith("-"):
                tpl = s[1:].strip().strip('"').strip("'")
                if tpl:
                    module_metrics["templates"].append(tpl)

        signal["controller_count"] += _to_int(module_metrics["controller_count"], 0)
        signal["service_count"] += _to_int(module_metrics["service_count"], 0)
        signal["repository_count"] += _to_int(module_metrics["repository_count"], 0)
        signal["template_count"] += _to_int(module_metrics["template_count"], 0)
        signal["endpoint_count"] += _to_int(module_metrics["endpoint_count"], 0)
        signal["endpoint_paths"].extend(module_metrics["endpoint_paths"])
        signal["templates"].extend(module_metrics["templates"])
        signal["modules"][module_key] = module_metrics

    signal["endpoint_paths"] = _uniq_keep_order(signal["endpoint_paths"])
    signal["templates"] = _uniq_keep_order(signal["templates"])
    return signal


def _infer_top2_ratio(candidates: List[dict], metrics: Dict[str, Any]) -> float:
    if "top2_score_ratio" in metrics:
        return max(0.0, min(1.0, _to_float(metrics.get("top2_score_ratio"), 0.0)))
    if len(candidates) < 2:
        return 0.0
    top1 = _to_float(candidates[0].get("score"), 0.0)
    top2 = _to_float(candidates[1].get("score"), 0.0)
    if top1 <= 0:
        return 0.0
    return max(0.0, min(1.0, top2 / top1))


def _extract_endpoint_keywords(endpoint_paths: List[str]) -> List[str]:
    words: List[str] = []
    for path in endpoint_paths[:20]:
        parts = [p for p in path.split("/") if p and "{" not in p and "}" not in p]
        if not parts:
            continue
        token = re.sub(r"[^a-zA-Z0-9_-]", "", parts[0].strip().lower())
        if token:
            words.append(token)
        if len(words) >= 3:
            break
    return _uniq_keep_order(words)[:3]


def _infer_web_path_hint(templates: List[str]) -> str:
    if not templates:
        return ""
    first = templates[0]
    marker = "templates/"
    idx = first.find(marker)
    if idx >= 0:
        return first[idx + len(marker):]
    return first


def _build_suggested_hints(
    candidates: List[dict],
    roots_info: List[dict],
    structure_signals: Dict[str, Any],
) -> Dict[str, Any]:
    top_candidate = candidates[0] if candidates else {}

    backend_package_hint = str(top_candidate.get("package_prefix") or "").strip()
    if not backend_package_hint and roots_info:
        backend_package_hint = str(roots_info[0].get("package_prefix") or "").strip()

    web_path_hint = _infer_web_path_hint(structure_signals.get("templates") or [])

    keyword_pool: List[str] = []
    module_key = str(top_candidate.get("module_key") or "").strip().lower()
    if module_key:
        keyword_pool.append(module_key)
    if backend_package_hint:
        keyword_pool.append(backend_package_hint.split(".")[-1].lower())
    keyword_pool.extend(_extract_endpoint_keywords(structure_signals.get("endpoint_paths") or []))

    keywords = [k for k in _uniq_keep_order(keyword_pool) if k and k != "controller"][:3]

    return {
        "identity": {
            "backend_package_hint": backend_package_hint,
            "web_path_hint": web_path_hint,
            "keywords": keywords,
        }
    }


def _build_action_suggestions(reasons: List[str], suggested_hints: Dict[str, Any]) -> List[str]:
    actions: List[str] = []
    identity = suggested_hints.get("identity", {}) if isinstance(suggested_hints, dict) else {}
    keywords = identity.get("keywords") if isinstance(identity, dict) else []

    if REASON_AMBIGUITY_RATIO_HIGH_NO_HINTS in reasons or REASON_TOP2_RATIO_AMBIGUOUS in reasons:
        if isinstance(keywords, list) and keywords:
            actions.append(f"provide --keywords '{','.join(str(k) for k in keywords[:3])}' and rerun discover")
        else:
            actions.append("provide --keywords and rerun discover to reduce ambiguity")

    if REASON_CONTROLLER_NO_ENDPOINT in reasons:
        actions.append("add identity.backend_package_hint and verify endpoint annotation style in declared profile")

    if REASON_CONFIDENCE_BELOW_MIN in reasons:
        actions.append("review calibration/hints_suggested.yaml and backfill declared identity hints")

    if not actions:
        actions.append("calibration passed; optional hints can still be reviewed for stability")

    return _uniq_keep_order(actions)


def _confidence_tier(confidence: float) -> str:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.6:
        return "medium"
    return "low"


def _format_hints_yaml(report: Dict[str, Any]) -> str:
    identity = report.get("suggested_hints", {}).get("identity", {})
    backend = str(identity.get("backend_package_hint", ""))
    web = str(identity.get("web_path_hint", ""))
    keywords = identity.get("keywords", [])
    reasons = report.get("reasons", [])

    lines = [
        "# workspace-only suggested hints (Round20 calibration)",
        "identity:",
        f"  backend_package_hint: \"{backend}\"",
        f"  web_path_hint: \"{web}\"",
        "  keywords:",
    ]
    if isinstance(keywords, list) and keywords:
        for kw in keywords[:3]:
            lines.append(f"    - \"{str(kw)}\"")
    else:
        lines.append('    - ""')

    lines.extend([
        "calibration:",
        f"  generated_at: \"{report.get('timestamp', '')}\"",
        f"  confidence: {report.get('confidence', 0.0)}",
        f"  confidence_tier: \"{report.get('confidence_tier', 'low')}\"",
        "  reasons:",
    ])
    if isinstance(reasons, list) and reasons:
        for reason in reasons:
            lines.append(f"    - \"{str(reason)}\"")
    else:
        lines.append('    - ""')
    return "\n".join(lines) + "\n"


def _format_markdown_report(report: Dict[str, Any]) -> str:
    lines = [
        "# Calibration Report",
        "",
        f"- generated_at: `{report.get('timestamp', '')}`",
        f"- needs_human_hint: `{1 if report.get('needs_human_hint') else 0}`",
        f"- confidence: `{report.get('confidence', 0.0):.4f}`",
        f"- confidence_tier: `{report.get('confidence_tier', 'low')}`",
        "",
        "## Reasons",
    ]
    reasons = report.get("reasons", [])
    if isinstance(reasons, list) and reasons:
        for reason in reasons:
            lines.append(f"- `{reason}`")
    else:
        lines.append("- `(none)`")

    lines.append("")
    lines.append("## Action Suggestions")
    actions = report.get("action_suggestions", [])
    if isinstance(actions, list) and actions:
        for action in actions:
            lines.append(f"- {action}")
    else:
        lines.append("- `(none)`")

    lines.append("")
    lines.append("## Suggested Hints")
    identity = report.get("suggested_hints", {}).get("identity", {})
    lines.append(f"- backend_package_hint: `{identity.get('backend_package_hint', '')}`")
    lines.append(f"- web_path_hint: `{identity.get('web_path_hint', '')}`")
    lines.append(f"- keywords: `{','.join(identity.get('keywords', []))}`")

    lines.append("")
    lines.append("## Metrics Snapshot")
    metrics_snapshot = report.get("metrics_snapshot", {})
    for key in sorted(metrics_snapshot.keys()):
        lines.append(f"- {key}: `{metrics_snapshot[key]}`")

    return "\n".join(lines) + "\n"


def run_calibration(
    workspace: Path,
    *,
    candidates: Optional[List[dict]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    roots_info: Optional[List[dict]] = None,
    structure_signals: Optional[Dict[str, Any]] = None,
    keywords: Optional[List[str]] = None,
    min_confidence: float = 0.60,
    ambiguity_threshold: float = 0.80,
    emit_hints: bool = True,
) -> Dict[str, Any]:
    """Run calibration and write workspace artifacts.

    Returns a dict with machine-readable calibration result fields.
    """
    workspace = Path(workspace).resolve()
    candidates = list(candidates or [])
    metrics = dict(metrics or {})
    roots_info = list(roots_info or [])
    structure_signals = dict(structure_signals or {})
    keywords = [str(k).strip() for k in (keywords or []) if str(k).strip()]

    if not candidates:
        candidates = _load_candidates_from_auto_discover(workspace)

    if not structure_signals:
        structure_signals = _load_structure_signals(workspace)

    controller_count = _to_int(structure_signals.get("controller_count"), 0)
    service_count = _to_int(structure_signals.get("service_count"), 0)
    repository_count = _to_int(structure_signals.get("repository_count"), 0)
    template_count = _to_int(structure_signals.get("template_count"), 0)
    endpoint_count = _to_int(
        structure_signals.get("endpoint_count", metrics.get("endpoints_total", 0)),
        _to_int(metrics.get("endpoints_total"), 0),
    )

    module_candidates = _to_int(metrics.get("module_candidates", len(candidates)), len(candidates))
    ambiguity_ratio = _to_float(metrics.get("ambiguity_ratio", 0.0), 0.0)
    top2_ratio = _infer_top2_ratio(candidates, metrics)
    top1_score = _to_float(candidates[0].get("score"), 0.0) if candidates else _to_float(metrics.get("top1_score"), 0.0)
    top2_score = _to_float(candidates[1].get("score"), 0.0) if len(candidates) > 1 else _to_float(metrics.get("top2_score"), 0.0)
    keywords_provided = bool(keywords)

    # Base confidence prefers top candidate confidence, then conservative fallback.
    if candidates:
        base_conf = _to_float(candidates[0].get("confidence"), 0.65)
        if base_conf > 1.0:
            base_conf = base_conf / 100.0
    else:
        base_conf = 0.45

    reasons: List[str] = []
    mandatory_reasons: List[str] = []

    if ambiguity_ratio >= float(ambiguity_threshold) and not keywords_provided:
        reasons.append(REASON_AMBIGUITY_RATIO_HIGH_NO_HINTS)
        mandatory_reasons.append(REASON_AMBIGUITY_RATIO_HIGH_NO_HINTS)
        base_conf -= 0.20

    if top2_ratio >= float(ambiguity_threshold):
        reasons.append(REASON_TOP2_RATIO_AMBIGUOUS)
        mandatory_reasons.append(REASON_TOP2_RATIO_AMBIGUOUS)
        base_conf -= min(0.30, 0.10 + max(0.0, top2_ratio - float(ambiguity_threshold)))

    if controller_count > 0 and endpoint_count == 0:
        reasons.append(REASON_CONTROLLER_NO_ENDPOINT)
        mandatory_reasons.append(REASON_CONTROLLER_NO_ENDPOINT)
        base_conf -= 0.30

    if module_candidates <= 0:
        reasons.append(REASON_NO_MODULE_CANDIDATE)
        base_conf -= 0.20

    confidence = max(0.0, min(1.0, round(base_conf, 4)))
    if confidence < float(min_confidence):
        reasons.append(REASON_CONFIDENCE_BELOW_MIN)

    reasons = _uniq_keep_order(reasons)
    needs_human_hint = bool(mandatory_reasons or confidence < float(min_confidence))
    confidence_tier = _confidence_tier(confidence)

    suggested_hints = _build_suggested_hints(candidates, roots_info, structure_signals)
    action_suggestions = _build_action_suggestions(reasons, suggested_hints)

    metrics_snapshot = {
        "module_candidates": module_candidates,
        "ambiguity_ratio": round(float(ambiguity_ratio), 4),
        "top1_score": round(float(top1_score), 4),
        "top2_score": round(float(top2_score), 4),
        "top2_score_ratio": round(float(top2_ratio), 4),
        "controller_count": controller_count,
        "service_count": service_count,
        "repository_count": repository_count,
        "template_count": template_count,
        "endpoint_count": endpoint_count,
        "keywords_provided": int(keywords_provided),
        "min_confidence": float(min_confidence),
        "ambiguity_threshold": float(ambiguity_threshold),
    }

    calibration_dir = workspace / "calibration"
    report_json_path = calibration_dir / "calibration_report.json"
    report_md_path = calibration_dir / "calibration_report.md"
    hints_path = calibration_dir / "hints_suggested.yaml"

    report = {
        "version": CALIBRATION_VERSION,
        "timestamp": _utc_now_iso(),
        "needs_human_hint": needs_human_hint,
        "confidence": confidence,
        "confidence_tier": confidence_tier,
        "reasons": reasons,
        "action_suggestions": action_suggestions,
        "suggested_hints": suggested_hints,
        "metrics_snapshot": metrics_snapshot,
    }

    _atomic_write_text(report_json_path, json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    _atomic_write_text(report_md_path, _format_markdown_report(report))

    if emit_hints:
        _atomic_write_text(hints_path, _format_hints_yaml(report))
        hints_path_value = str(hints_path)
    else:
        hints_path_value = ""

    report["report_path"] = str(report_md_path)
    report["report_json_path"] = str(report_json_path)
    report["suggested_hints_path"] = hints_path_value

    # Keep a stable minimum shape for plugin contract fields.
    report.setdefault("suggested_hints", {"identity": {"backend_package_hint": "", "web_path_hint": "", "keywords": []}})

    return report
