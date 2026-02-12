# A3 R27 Rollback Plan

## Fast fallback (no file revert)
- Disable additive machine-line json token while preserving legacy fields:
  - `export HONGZHI_MACHINE_JSON_ENABLE=0`

## Minimal rollback files
1. `prompt-dsl-system/tools/hongzhi_plugin.py`
- revert machine-json CLI switch, unified json fields, deterministic sort, mismatch_suggestion additions

2. `prompt-dsl-system/tools/scan_graph.py`
- revert mismatch enum rename if needed

3. `prompt-dsl-system/tools/hongzhi_ai_kit/paths.py`
- revert resolver wrapper normalization

4. `prompt-dsl-system/tools/golden_path_regression.sh`
- remove Phase33 block

5. Docs
- `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
- `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
- `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`

6. Artifacts to remove
- `prompt-dsl-system/tools/artifacts/A1_R27_impact_tree.md`
- `prompt-dsl-system/tools/artifacts/A2_R27_change_ledger.md`
- `prompt-dsl-system/tools/artifacts/A3_R27_rollback_plan.md`
- `prompt-dsl-system/tools/artifacts/A4_R27_cleanup_report.md`
- `prompt-dsl-system/tools/artifacts/R27_perf_notes.md`

## Post-rollback verification
1. `./prompt-dsl-system/tools/run.sh validate --repo-root .`
2. `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
3. `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`
