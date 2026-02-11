# A3 R16 Rollback Plan

## Rollback Target

Revert Round16 additions: capability registry, smart incremental, contract v3, and regression phases 20-22.

## Steps

1. Remove new helper files:
   - `prompt-dsl-system/tools/hongzhi_ai_kit/capability_store.py`
   - `prompt-dsl-system/tools/hongzhi_ai_kit/paths.py`
2. Revert plugin runner:
   - `prompt-dsl-system/tools/hongzhi_plugin.py`
   - `prompt-dsl-system/tools/hongzhi_ai_kit/__init__.py`
3. Revert regression script:
   - remove Phase20~22 and restore pre-R16 checks
4. Revert docs/baselines:
   - `PLUGIN_RUNNER.md`
   - `FACT_BASELINE.md`
   - `COMPLIANCE_MATRIX.md`
   - `HONGZHI_COMPANY_CONSTITUTION.md` Rule 18
5. Optional cleanup of generated runtime state:
   - remove `capability_index.json`
   - remove `<fp>/latest.json`
   - remove `<fp>/runs/<run_id>/run_meta.json`

## Verification After Rollback

1. Run:
   - `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`
2. Ensure regression returns to pre-R16 expectations.
3. Verify plugin still enforces governance/read-only baseline.
