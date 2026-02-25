#!/usr/bin/env python3
"""Company profile loader and parameter injection.

Extracted from pipeline_runner.py for modularity.
Handles loading company_profile.yaml and injecting defaults
into pipeline step parameters (additive-only policy).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pipeline_yaml_parser import ParseError, parse_simple_yaml_two_level


def load_company_profile(profile_path: Path) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Load and parse a company profile YAML file, returning (profile, warnings)."""
    warnings: List[str] = []
    if not profile_path.exists():
        warnings.append(f"Company profile not found: {profile_path}")
        return None, warnings

    try:
        raw = profile_path.read_text(encoding="utf-8")
    except OSError as exc:
        warnings.append(f"Company profile read failed: {exc}")
        return None, warnings

    try:
        parsed = parse_simple_yaml_two_level(raw)
    except ParseError as exc:
        warnings.append(f"Company profile parse failed: {exc}")
        return None, warnings

    return parsed, warnings


def profile_effective_defaults(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract effective default parameters from a company profile's db_execution section."""
    if not isinstance(profile, dict):
        return {}

    db_execution = profile.get("db_execution")
    if not isinstance(db_execution, dict):
        return {}

    defaults: Dict[str, Any] = {}

    schema_strategy = db_execution.get("default_schema_strategy")
    if schema_strategy not in (None, ""):
        defaults["schema_strategy"] = schema_strategy

    preferred_dm_tool = db_execution.get("preferred_dm_tool")
    preferred_oracle_tool = db_execution.get("preferred_oracle_tool")
    if preferred_dm_tool not in (None, "") or preferred_oracle_tool not in (None, ""):
        if preferred_dm_tool not in (None, "") and preferred_oracle_tool not in (None, ""):
            defaults["execution_tool"] = {
                "dm8": preferred_dm_tool,
                "oracle": preferred_oracle_tool,
            }
        elif preferred_dm_tool not in (None, ""):
            defaults["execution_tool"] = preferred_dm_tool
        else:
            defaults["execution_tool"] = preferred_oracle_tool

    require_precheck_gate = db_execution.get("require_precheck_gate")
    if require_precheck_gate is not None:
        defaults["require_precheck_gate"] = require_precheck_gate

    return defaults


def detect_target_db(params: Dict[str, Any]) -> str:
    """Detect the target database type from step parameters; defaults to 'dm8'."""
    target_db = params.get("target_db")
    if isinstance(target_db, str) and target_db.strip():
        target_db_norm = target_db.strip().lower()
        if "oracle" in target_db_norm:
            return "oracle"
        if "dm" in target_db_norm:
            return "dm8"

    objective = params.get("objective")
    if isinstance(objective, str):
        objective_norm = objective.lower()
        if "oracle" in objective_norm:
            return "oracle"
        if "dm8" in objective_norm:
            return "dm8"

    return "dm8"


def choose_profile_execution_tool(profile: Optional[Dict[str, Any]], target_db: str) -> Optional[Any]:
    """Select the preferred execution tool from a company profile based on the target database."""
    if not isinstance(profile, dict):
        return None
    db_execution = profile.get("db_execution")
    if not isinstance(db_execution, dict):
        return None

    if target_db == "oracle":
        preferred_oracle_tool = db_execution.get("preferred_oracle_tool")
        if preferred_oracle_tool not in (None, ""):
            return preferred_oracle_tool

    preferred_dm_tool = db_execution.get("preferred_dm_tool")
    if preferred_dm_tool not in (None, ""):
        return preferred_dm_tool

    if target_db != "oracle":
        preferred_oracle_tool = db_execution.get("preferred_oracle_tool")
        if preferred_oracle_tool not in (None, ""):
            return preferred_oracle_tool

    return None


def inject_profile_defaults(
    params: Dict[str, Any], profile: Optional[Dict[str, Any]]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Inject company profile defaults into step params (additive-only). Returns (updated, injected)."""
    updated = dict(params)
    injected: Dict[str, Any] = {}

    if not isinstance(profile, dict):
        return updated, injected

    db_execution = profile.get("db_execution")
    if not isinstance(db_execution, dict):
        return updated, injected

    if "schema_strategy" not in updated:
        schema_strategy = db_execution.get("default_schema_strategy")
        if schema_strategy not in (None, ""):
            updated["schema_strategy"] = schema_strategy
            injected["schema_strategy"] = schema_strategy

    if "execution_tool" not in updated:
        target_db = detect_target_db(updated)
        execution_tool = choose_profile_execution_tool(profile, target_db)
        if execution_tool not in (None, ""):
            updated["execution_tool"] = execution_tool
            injected["execution_tool"] = execution_tool

    if "require_precheck_gate" not in updated:
        require_precheck_gate = db_execution.get("require_precheck_gate")
        if require_precheck_gate is not None:
            updated["require_precheck_gate"] = require_precheck_gate
            injected["require_precheck_gate"] = require_precheck_gate

    return updated, injected
