# A2_R20_change_ledger

## Baseline
- Baseline strict validate before R20: PASS (`Errors=0`, `Warnings=0`).
- Baseline regression before R20: `54/54 PASS`.

## Code Changes
- Added `prompt-dsl-system/tools/calibration_engine.py`.
  - Introduced calibration report generation:
    - `calibration/calibration_report.json`
    - `calibration/calibration_report.md`
    - `calibration/hints_suggested.yaml` (toggleable)
  - Added machine-readable fields:
    - `needs_human_hint`
    - `confidence`
    - `confidence_tier`
    - `reasons[]`
    - `suggested_hints`
    - `metrics_snapshot`
- Updated `prompt-dsl-system/tools/hongzhi_plugin.py`.
  - Added discover calibration execution hook and fallback path.
  - Added discover CLI flags:
    - `--min-confidence` (default `0.60`)
    - `--ambiguity-threshold` (default `0.80`)
    - `--emit-hints` / `--no-emit-hints`
  - Added strict exit code `21` when `needs_human_hint=true`.
  - Extended summary line fields:
    - `needs_human_hint`
    - `confidence_tier`
    - `ambiguity_ratio`
    - `exit_hint`
  - Extended capabilities outputs (`json`/`jsonl`) with `calibration` data.
- Added fixtures:
  - `prompt-dsl-system/tools/_tmp_structure_cases/case4_endpoint_miss/`
  - `prompt-dsl-system/tools/_tmp_structure_cases/case5_ambiguous_two_modules/`
- Updated regression script `prompt-dsl-system/tools/golden_path_regression.sh`.
  - Added Phase26 checks:
    1. `calibration_low_confidence_exit21_strict`
    2. `calibration_non_strict_warn_exit0`
    3. `calibration_outputs_exist_in_workspace`
    4. `capabilities_contains_calibration_fields`

## Docs/Baseline Changes
- `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
- `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
- `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`

## Verification Evidence
- `./prompt-dsl-system/tools/run.sh validate --repo-root .` -> PASS (`Errors=0`, `Warnings=0`)
- `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .` -> PASS (`Errors=0`, `Warnings=0`)
- `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .` -> `58/58 PASS` (OVERALL PASS)

## Compatibility Notes
- Existing machine lines (`HONGZHI_CAPS`, `HONGZHI_STATUS`, `HONGZHI_GOV_BLOCK`) are preserved.
- Existing capabilities fields are preserved; calibration fields are additive.
