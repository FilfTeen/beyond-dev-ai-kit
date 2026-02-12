# A3_R29 Rollback Plan

## Rollback Goal
Revert only Round29 additive changes while preserving Round28 baseline behavior.

## Minimal File Set to Revert
1. `prompt-dsl-system/tools/hongzhi_plugin.py`
- Remove company scope runtime helpers and `exit=26` gate.
- Remove additive `company_scope` fields from machine lines/summary/capabilities/jsonl.

2. `prompt-dsl-system/tools/contract_schema_v1.json`
- Remove `company_scope` from required fields/json required keys.
- Remove exit code 26 mapping.

3. `prompt-dsl-system/05_skill_registry/skills.json`
- Restore previous lifecycle statuses if required (governance skills back to previous state).

4. `prompt-dsl-system/tools/golden_path_regression.sh`
- Remove Phase35 checks.

5. Docs/constitution
- Revert Round29 additions in:
  - `PLUGIN_RUNNER.md`
  - `FACT_BASELINE.md`
  - `COMPLIANCE_MATRIX.md`
  - `HONGZHI_COMPANY_CONSTITUTION.md`

## Verification After Rollback
1. `./prompt-dsl-system/tools/run.sh validate --repo-root .`
2. `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
3. `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`

Expected:
- Regression total returns to pre-R29 baseline (`112`) with full pass.
- No `company_scope` hard-gate behavior.
