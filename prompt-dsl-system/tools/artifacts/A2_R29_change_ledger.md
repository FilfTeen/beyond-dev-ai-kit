# A2_R29 Change Ledger

## Baseline
- Pre-R29 regression: `112/112 PASS`.

## Implemented Changes
1. `prompt-dsl-system/tools/hongzhi_plugin.py`
- Added constants/envs:
  - `COMPANY_SCOPE_DEFAULT=hongzhi-work-dev`
  - `HONGZHI_COMPANY_SCOPE`
  - `HONGZHI_REQUIRE_COMPANY_SCOPE`
  - `COMPANY_SCOPE_EXIT_CODE=26`
- Added runtime helpers:
  - `set_company_scope_runtime(...)`
  - `company_scope_runtime()`
  - `company_scope_required_runtime()`
  - `check_company_scope_gate(...)`
- Machine-line additive updates:
  - all `HONGZHI_*` machine lines include `company_scope=...`.
  - machine JSON payload includes `company_scope`.
- Summary/capabilities/journal additive updates:
  - `hongzhi_ai_kit_summary` includes `company_scope`.
  - `capabilities.json` top-level includes `company_scope`.
  - `capabilities.jsonl` records include `company_scope`.
- Optional hard gate:
  - when required and mismatch => `HONGZHI_GOV_BLOCK reason=company_scope_mismatch`, `exit=26`.

2. `prompt-dsl-system/tools/contract_schema_v1.json`
- Added `company_scope` to machine-line required fields.
- Added `company_scope` to json payload required keys.
- Added exit code mapping `26: company_scope_mismatch`.

3. `prompt-dsl-system/05_skill_registry/skills.json`
- Converged governance plugin skills from `staging` to `deployed`.

4. `prompt-dsl-system/tools/golden_path_regression.sh`
- Added Phase35 (6 checks):
  - `Phase35:governance_skills_deployed`
  - `Phase35:machine_lines_include_company_scope`
  - `Phase35:company_scope_gate_default_off`
  - `Phase35:company_scope_mismatch_block_exit26`
  - `Phase35:company_scope_mismatch_zero_write`
  - `Phase35:company_scope_match_required_allows`

5. Docs
- Updated `PLUGIN_RUNNER.md`, `FACT_BASELINE.md`, `COMPLIANCE_MATRIX.md`.
- Updated constitution with Rule 20.

## Validation
- `validate`: PASS (`Errors=0, Warnings=0`)
- `strict validate`: PASS (`Errors=0, Warnings=0`)
- `golden regression`: `118/118 PASS`.
