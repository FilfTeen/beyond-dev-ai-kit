# A3_R18_rollback_plan

## Scope
Rollback Round18 changes if any downstream incompatibility is found.

## Rollback Steps
1. Revert runtime contract changes in `prompt-dsl-system/tools/hongzhi_plugin.py`:
   - Remove version-triplet fields from `HONGZHI_CAPS` and `HONGZHI_GOV_BLOCK`.
   - Remove `HONGZHI_STATUS` line.
   - Restore previous capabilities payload fields if needed.
2. Revert guard adjustments:
   - `prompt-dsl-system/tools/path_diff_guard.py`
   - `prompt-dsl-system/tools/guardrails.yaml`
3. Revert regression Phase24 block in `prompt-dsl-system/tools/golden_path_regression.sh`.
4. Revert Round18 docs/baselines:
   - `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
   - `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
   - `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`
   - `README.md` (if not desired)
5. Remove Round18 closure artifacts:
   - `prompt-dsl-system/tools/artifacts/A1_R18_impact_tree.md`
   - `prompt-dsl-system/tools/artifacts/A2_R18_change_ledger.md`
   - `prompt-dsl-system/tools/artifacts/A3_R18_rollback_plan.md`
   - `prompt-dsl-system/tools/artifacts/A4_R18_cleanup_report.md`
   - `prompt-dsl-system/tools/artifacts/R18_release_notes.md`

## Post-Rollback Verification
- Run:
  - `./prompt-dsl-system/tools/run.sh validate --repo-root .`
  - `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
  - `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`
- Confirm expected baseline check count for the target rollback point.
