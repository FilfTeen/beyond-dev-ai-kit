# A3_R20_rollback_plan

## Rollback Scope (Round20 only)
1. Remove calibration engine file:
   - `prompt-dsl-system/tools/calibration_engine.py`
2. Revert discover calibration integration and exit21 changes in:
   - `prompt-dsl-system/tools/hongzhi_plugin.py`
   - remove CLI flags: `--min-confidence`, `--ambiguity-threshold`, `--emit-hints`, `--no-emit-hints`
   - remove summary/calibration fields added by R20
3. Remove new fixtures:
   - `prompt-dsl-system/tools/_tmp_structure_cases/case4_endpoint_miss/`
   - `prompt-dsl-system/tools/_tmp_structure_cases/case5_ambiguous_two_modules/`
4. Revert regression additions:
   - remove Phase26 checks from `prompt-dsl-system/tools/golden_path_regression.sh`
5. Revert documentation/baseline updates:
   - `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
   - `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
   - `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`
6. Remove closure artifacts:
   - `prompt-dsl-system/tools/artifacts/A1_R20_impact_tree.md`
   - `prompt-dsl-system/tools/artifacts/A2_R20_change_ledger.md`
   - `prompt-dsl-system/tools/artifacts/A3_R20_rollback_plan.md`
   - `prompt-dsl-system/tools/artifacts/R20_accuracy_notes.md`

## Post-rollback Verification
- `./prompt-dsl-system/tools/run.sh validate --repo-root .`
- `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
- `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`
- Expected: regression count returns to pre-R20 baseline (`54` checks).
