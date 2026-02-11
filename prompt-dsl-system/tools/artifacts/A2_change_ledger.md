# A2 Change Ledger

## Code

- Updated `pyproject.toml` version `3.1.0 -> 4.0.0` to match runner/package runtime version.
- Added `setup.py` for editable install compatibility with older pip flows.
- Updated `prompt-dsl-system/tools/hongzhi_ai_kit/cli.py`:
  - installed-first module import
  - source-tree fallback import
  - actionable install hint on failure
- Updated `prompt-dsl-system/tools/hongzhi_plugin.py`:
  - v4 contract outputs (`HONGZHI_CAPS`, `HONGZHI_GOV_BLOCK`)
  - append-only `capabilities.jsonl`
  - retained v3 summary output
- Updated guard behavior in `prompt-dsl-system/tools/path_diff_guard.py` and `prompt-dsl-system/tools/guardrails.yaml`:
  - allow top-level packaging files without module path
  - ignore `_regression_tmp` noise in guard checks

## Skills/Pipelines

- Added `prompt-dsl-system/05_skill_registry/skills/governance/skill_governance_plugin_runner.yaml`.
- Updated `prompt-dsl-system/05_skill_registry/skills.json` (new staging entry).
- Added `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_plugin_discover.md`.
- Fixed Step0 required handoff fields in `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_module_migration.md`.

## Regression/Docs

- Enhanced `prompt-dsl-system/tools/golden_path_regression.sh` with Phase23 checks and uninstalled install-hint check.
- Updated `prompt-dsl-system/tools/PLUGIN_RUNNER.md` install/contract docs.
- Updated `prompt-dsl-system/00_conventions/FACT_BASELINE.md` and `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`.
