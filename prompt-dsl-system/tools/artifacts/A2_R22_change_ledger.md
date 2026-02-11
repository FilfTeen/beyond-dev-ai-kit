# A2_R22_change_ledger

## Changed Files
- Modified:
  - `prompt-dsl-system/tools/hongzhi_plugin.py`
  - `prompt-dsl-system/tools/golden_path_regression.sh`
  - `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
  - `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
  - `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`
- Added:
  - `prompt-dsl-system/tools/hongzhi_ai_kit/hint_bundle.py`

## Key Behavior Changes
- Discover hint bundle is now typed (`kind=profile_delta`) and machine-verifiable.
- `--apply-hints` accepts path or inline JSON.
- Strict deterministic exits:
  - `21` for calibration needs_human_hint
  - `22` for hint verify failure (e.g., expired bundle)
  - `23` for token scope missing `hint_bundle`
- Added machine line for scope block:
  - `HONGZHI_HINTS_BLOCK code=23 reason=token_scope_missing ...`
- Capabilities additive field:
  - `hint_bundle {kind,path,verified,expired,ttl_seconds,created_at,expires_at}`

## Verification Evidence
- `./prompt-dsl-system/tools/run.sh validate --repo-root .`
  - Errors=0, Warnings=0
- `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
  - Errors=0, Warnings=0
- `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`
  - 70/70 PASS, includes new Phase28 checks.
