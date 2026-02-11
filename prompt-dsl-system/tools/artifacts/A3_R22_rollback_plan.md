# A3_R22_rollback_plan

## Objective
Rollback Round22 hint assetization with minimum disruption and restore Round21 behavior.

## Steps
1. Remove new helper module:
   - `prompt-dsl-system/tools/hongzhi_ai_kit/hint_bundle.py`
2. Revert Round22 edits in:
   - `prompt-dsl-system/tools/hongzhi_plugin.py`
   - `prompt-dsl-system/tools/golden_path_regression.sh` (remove Phase28)
   - `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
   - `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
   - `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`
3. Re-run gates:
   - `./prompt-dsl-system/tools/run.sh validate --repo-root .`
   - `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
   - `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`
4. Confirm regression total returns to pre-R22 baseline and all PASS.

## Safety
- Rollback does not require writes to any external target repo_root.
- Governance pre-dispatch deny semantics remain intact across rollback.
