# A1_R28 Impact Tree

## Objective
- Solidify machine-line contract into explicit schema + zero-dependency validator.
- Add regression hard gate (Phase34) without breaking Phase1~Phase33.

## Change Surface
- Added `prompt-dsl-system/tools/contract_schema_v1.json`.
- Added `prompt-dsl-system/tools/contract_validator.py`.
- Extended `prompt-dsl-system/tools/golden_path_regression.sh` with Phase34 (6 checks).
- Updated docs/baselines (PLUGIN_RUNNER/FACT_BASELINE/COMPLIANCE_MATRIX).

## Impact Paths
- Output contract verification now executable from stdout/logs.
- Governance/block/mismatch machine lines are schema-validated.
- Additive policy guard introduced for future schema evolution.

## Non-Goals / Preserved
- No semantic changes to existing machine line fields.
- No relaxation of governance zero-write/read-only contract.
- No third-party dependency introduced.
