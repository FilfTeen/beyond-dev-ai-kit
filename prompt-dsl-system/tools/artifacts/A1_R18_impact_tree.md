# A1_R18_impact_tree

## Goal
Round18: make `hongzhi_ai_kit` release-grade with version-triplet contract, zero-write governance integrity, and packaging/build regression gates.

## Impact Tree
- Packaging Surface
  - `pyproject.toml` (already 4.0.0 packaging baseline retained)
  - `README.md` (top-level install/entry quickstart for sdist/wheel hygiene)
- Runtime Contract Surface
  - `prompt-dsl-system/tools/hongzhi_plugin.py`
    - Add explicit version triplet: `package_version`, `plugin_version`, `contract_version`
    - Extend `HONGZHI_CAPS` line with version fields
    - Extend `HONGZHI_GOV_BLOCK` line with version fields
    - Add `HONGZHI_STATUS` machine line
    - Persist version triplet into `capabilities.json` and `capabilities.jsonl`
- Guard/Governance Surface
  - `prompt-dsl-system/tools/path_diff_guard.py`
    - Fix dotfile normalization bug (`.gitignore`/`.DS_Store` no longer stripped)
    - Allow top-level `.gitignore` as packaging hygiene file
    - Ignore `dist/**` for local build artifacts
  - `prompt-dsl-system/tools/guardrails.yaml`
    - Add `dist` and top-level `.DS_Store` ignore patterns
- Regression Surface
  - `prompt-dsl-system/tools/golden_path_regression.sh`
    - Add Phase24 (5 checks): version triplet, wheel install smoke, sdist build smoke, gitignore guard, gov block version+zero-write
    - Harden wheel smoke against `PYTHONPATH` pollution by forcing isolated pip install and runtime checks
- Documentation/Baseline Surface
  - `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
  - `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
  - `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`

## Risk Notes
- Build/packaging checks now execute in regression; runtime cost increases moderately.
- Guard fix changes dotfile handling globally in path guard; covered by validate+regression full pass.
