# A3_R23_rollback_plan

## Objective
Rollback Round23 Capability Index Federation with minimal blast radius.

## Rollback Steps
1. Remove federated index helper module:
   - delete `prompt-dsl-system/tools/hongzhi_ai_kit/federated_store.py`
2. Revert plugin runtime integration:
   - rollback `prompt-dsl-system/tools/hongzhi_plugin.py` changes for:
     - `INDEX_SCOPE_EXIT_CODE=24`
     - `HONGZHI_INDEX` / `HONGZHI_INDEX_BLOCK`
     - `index` subcommands
     - federated write hooks in discover/diff/profile/migrate
3. Revert regression additions:
   - remove Phase29 from `prompt-dsl-system/tools/golden_path_regression.sh`
4. Revert docs/baselines:
   - `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
   - `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
   - `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`
5. Remove Round23 artifacts:
   - `A1_R23_impact_tree.md`
   - `A2_R23_change_ledger.md`
   - `A3_R23_rollback_plan.md`
   - `A4_R23_cleanup_report.md`
   - `R23_index_federation_spec.md`

## Post-Rollback Validation
- Run:
  - `./prompt-dsl-system/tools/run.sh validate --repo-root .`
  - `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
  - `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`
- Expected: all checks pass and no Phase29 checks remain.
