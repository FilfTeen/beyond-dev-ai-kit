# A2_R18_change_ledger

## Round18 Change Ledger

## Code
- Updated `prompt-dsl-system/tools/hongzhi_plugin.py`
  - Introduced version triplet helper.
  - `status` now emits:
    - human-readable version lines
    - `HONGZHI_STATUS package_version=... plugin_version=... contract_version=... enabled=...`
  - `HONGZHI_CAPS` now emits path + version triplet.
  - `HONGZHI_GOV_BLOCK` now emits version triplet while keeping original exit code semantics.
  - `capabilities.json` adds explicit `package_version`/`plugin_version` and keeps backward-compatible `version` key.
  - `capabilities.jsonl` appends version triplet per run record.

- Updated `prompt-dsl-system/tools/path_diff_guard.py`
  - Fixed `normalize_rel()` dotfile bug.
  - Added `dist` ignore defaults.
  - Added `.gitignore` to top-level packaging allowlist.

- Updated `prompt-dsl-system/tools/guardrails.yaml`
  - Added ignore entries for `dist` and top-level `.DS_Store`.

- Updated `prompt-dsl-system/tools/golden_path_regression.sh`
  - Added Phase24 with 5 checks.
  - Added isolation hardening for wheel smoke (`PYTHONPATH=""` + `--force-reinstall`).

## Docs/Baseline
- Updated `prompt-dsl-system/tools/PLUGIN_RUNNER.md` for R18 version-triplet contract.
- Updated `prompt-dsl-system/00_conventions/FACT_BASELINE.md` (47-check baseline + R18 facts).
- Updated `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md` (R20 row + 47-check mapping).
- Added `README.md` at repo root for packaging discoverability.

## Hygiene
- Updated `.gitignore` with macOS/python/tooling-generated patterns.
- Removed tracked `.DS_Store`/`__pycache__` pollution from index.

## Verification
- `./prompt-dsl-system/tools/run.sh validate --repo-root .` PASS.
- `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .` PASS.
- `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .` PASS (47/47).
