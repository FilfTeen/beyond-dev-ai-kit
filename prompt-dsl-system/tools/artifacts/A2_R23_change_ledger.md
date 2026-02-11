# A2_R23_change_ledger

## Changed Files
- Added:
  - `prompt-dsl-system/tools/hongzhi_ai_kit/federated_store.py`
  - `prompt-dsl-system/tools/artifacts/A1_R23_impact_tree.md`
  - `prompt-dsl-system/tools/artifacts/A2_R23_change_ledger.md`
  - `prompt-dsl-system/tools/artifacts/A3_R23_rollback_plan.md`
  - `prompt-dsl-system/tools/artifacts/A4_R23_cleanup_report.md`
  - `prompt-dsl-system/tools/artifacts/R23_index_federation_spec.md`
- Modified:
  - `prompt-dsl-system/tools/hongzhi_plugin.py`
  - `prompt-dsl-system/tools/golden_path_regression.sh`
  - `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
  - `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
  - `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`

## Key Behavior Changes
- Federated index persisted in global state (atomic):
  - `federated_index.json`
  - `federated_index.jsonl` (optional)
  - `repos/<fp>/index.json` (optional mirror)
- Discover/diff/profile/migrate successful runs can update federated index and emit:
  - `HONGZHI_INDEX <abs_path> ...`
- Independent federated scope gate:
  - missing `federated_index` scope with token:
    - strict => `exit=24` + `HONGZHI_INDEX_BLOCK ...`
    - non-strict => WARN + no federated write
- New CLI:
  - `hongzhi-ai-kit index list`
  - `hongzhi-ai-kit index query --keyword ... --endpoint ... --top-k ...`
  - `hongzhi-ai-kit index explain <fp> <run_id>`
- capabilities writes switched to atomic JSON write; capabilities.jsonl switched to atomic append path.

## Verification Evidence
- `./prompt-dsl-system/tools/run.sh validate --repo-root .`
- result: `Errors=0, Warnings=0`
- `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
- result: `Errors=0, Warnings=0`
- `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`
- result: `78/78 PASS` (`OVERALL: PASS`)
- Regression includes new Phase29 checks (8 new checks).
