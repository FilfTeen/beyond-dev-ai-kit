# A1_R22_impact_tree

## Goal
Round22 upgrades discover Hint Loop into **Hint Assetization (Profile Delta Bundle)** with deterministic strict exits and scope-aware governance.

## Impact Tree
- Runtime core
  - `prompt-dsl-system/tools/hongzhi_plugin.py`
    - Added strict exit codes:
      - `22`: hint verify failed (expired/invalid/mismatch)
      - `23`: hint bundle scope blocked
    - Added machine line:
      - `HONGZHI_HINTS_BLOCK ...`
    - Added hint-bundle apply path:
      - `--apply-hints <path-or-inline-json>`
      - `--allow-cross-repo-hints`
      - `--hint-bundle-ttl-seconds`
    - Added profile_delta bundle lifecycle:
      - emit on low-confidence strict hint loop
      - verify on apply (scope/ttl/fingerprint)
      - merge into discover effective inputs
    - Extended summary fields:
      - `hint_bundle_kind`, `hint_verified`, `hint_expired`
- Package helpers
  - `prompt-dsl-system/tools/hongzhi_ai_kit/hint_bundle.py` (new)
    - profile_delta schema build/load/verify
    - supports file path and inline JSON input
- Regression gate
  - `prompt-dsl-system/tools/golden_path_regression.sh`
    - Added Phase28 with six checks for bundle schema/apply/expiry/scope/gating
- Docs/baseline
  - `PLUGIN_RUNNER.md`, `FACT_BASELINE.md`, `COMPLIANCE_MATRIX.md`

## Risk Notes
- Backward compatibility preserved:
  - existing `HONGZHI_CAPS`, `HONGZHI_STATUS`, `HONGZHI_GOV_BLOCK`, summary line kept
  - v4 fields retained; only additive fields introduced
- Governance block (10/11/12) remains pre-dispatch hard gate with zero writes.
