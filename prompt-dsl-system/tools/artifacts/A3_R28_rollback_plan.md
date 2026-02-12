# A3_R28 Rollback Plan

## Scope
Rollback only Round28 additions.

## Files to Revert
- `prompt-dsl-system/tools/contract_schema_v1.json` (delete)
- `prompt-dsl-system/tools/contract_validator.py` (delete)
- `prompt-dsl-system/tools/golden_path_regression.sh` (remove Phase34 block)
- `prompt-dsl-system/tools/PLUGIN_RUNNER.md` (revert Round28 contract-validator section)
- `prompt-dsl-system/00_conventions/FACT_BASELINE.md` (restore pre-R28 counts/sections)
- `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md` (remove R30 row and 112-check references)
- Round28 artifacts:
  - `A1_R28_impact_tree.md`
  - `A2_R28_change_ledger.md`
  - `A3_R28_rollback_plan.md`
  - `A4_R28_cleanup_report.md`

## Verification After Rollback
1. `./prompt-dsl-system/tools/run.sh validate --repo-root .`
2. `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
3. `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`

Expected: regression total returns to pre-R28 baseline and all pass.
