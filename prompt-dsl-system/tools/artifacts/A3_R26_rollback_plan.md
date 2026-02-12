# A3 R26 Rollback Plan

## Goal
Rollback only R26 additive changes with minimum blast radius.

## Immediate Safe Fallback (No code revert)
1. Disable machine-line `json='...'` token output temporarily:
- `export HONGZHI_MACHINE_JSON_ENABLE=0`

This preserves legacy fields (`path=...`, version tokens, summary line) and can be used as emergency compatibility mode.

## Minimal File Rollback Set
1. Revert R26 scan graph contract additions:
- `prompt-dsl-system/tools/scan_graph.py`

2. Revert R26 plugin additive contract/reuse changes:
- `prompt-dsl-system/tools/hongzhi_plugin.py`

3. Revert Phase32 checks:
- `prompt-dsl-system/tools/golden_path_regression.sh`

4. Revert docs/baselines:
- `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
- `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
- `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`

5. Remove R26 closure artifacts:
- `prompt-dsl-system/tools/artifacts/A1_R26_impact_tree.md`
- `prompt-dsl-system/tools/artifacts/A2_R26_change_ledger.md`
- `prompt-dsl-system/tools/artifacts/A3_R26_rollback_plan.md`
- `prompt-dsl-system/tools/artifacts/A4_R26_cleanup_report.md`
- `prompt-dsl-system/tools/artifacts/R26_perf_notes.md`
- `prompt-dsl-system/tools/artifacts/R26_contract_notes.md`

## Verification After Rollback
1. `./prompt-dsl-system/tools/run.sh validate --repo-root .`
2. `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
3. `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`

Expected: return to pre-R26 baseline behavior and check set.
