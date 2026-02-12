# A2_R28 Change Ledger

## Baseline
- Pre-change regression: `106/106 PASS`.

## Implemented Changes
1. New schema file: `prompt-dsl-system/tools/contract_schema_v1.json`
   - Defines machine lines, required fields, json payload keys, enums, exit-code mapping, additive policy.
2. New validator: `prompt-dsl-system/tools/contract_validator.py`
   - Inputs: `--schema`, `--stdin`, `--file`, `--baseline-schema`.
   - Output: `CONTRACT_OK=1` / `CONTRACT_OK=0`.
   - Exit: `0` on pass, `2` on fail.
3. Regression update: `prompt-dsl-system/tools/golden_path_regression.sh`
   - Added Phase34 checks:
     - contract_schema_exists_and_valid_json
     - contract_validator_smoke
     - contract_validator_on_discover_stdout
     - contract_validator_on_gov_block_stdout
     - contract_validator_on_exit25_mismatch_stdout
     - contract_schema_additive_guard
4. Docs updated:
   - `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
   - `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
   - `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`

## Validation Results
- validate: PASS (`Errors=0`, `Warnings=0`)
- strict validate: PASS (`Errors=0`, `Warnings=0`)
- regression: `112/112 PASS` (Phase34 included)
