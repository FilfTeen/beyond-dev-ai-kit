# A2_R19_change_ledger

## Code Changes
- `prompt-dsl-system/tools/hongzhi_plugin.py`
  - Added governance/token helpers:
    - `parse_permit_token`, `validate_permit_token`, `compute_policy_hash`
    - realpath checks via `canonical_path` and `is_path_within`
  - Added limits helpers:
    - `build_scan_stats`, `evaluate_limits`
  - Enforced limits contract:
    - non-strict: warn + `limits_hit=true`
    - strict: `exit=20`
  - Enriched capabilities outputs and jsonl records.
  - Upgraded capability registry entry structure (v1 fields per project entry).
- `prompt-dsl-system/tools/golden_path_regression.sh`
  - Added Phase25 checks:
    - token_ttl_expired_block
    - token_scope_block
    - symlink_bypass_denied
    - limits_hit_normal_warn
    - limits_hit_strict_fail
    - capability_index_gated_by_governance
    - pipeline_status_decide_discover_smoke
- `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_plugin_discover.md`
  - Reworked to `status -> decide -> discover` hard-gate flow.
- `prompt-dsl-system/05_skill_registry/skills/governance/skill_governance_plugin_status.yaml`
  - Added new read-only governance preflight skill.
- `prompt-dsl-system/05_skill_registry/skills.json`
  - Registered `skill_governance_plugin_status`.
- Docs/conventions updates:
  - `PLUGIN_RUNNER.md`
  - `FACT_BASELINE.md`
  - `COMPLIANCE_MATRIX.md`
  - `HONGZHI_COMPANY_CONSTITUTION.md` (Rule 19)

## Validation Results
- validate: PASS (`Errors=0`, `Warnings=0`)
- strict validate: PASS (`Errors=0`, `Warnings=0`)
- regression: PASS (`54/54`)
