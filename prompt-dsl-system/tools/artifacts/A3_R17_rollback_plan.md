# A3 R17 Rollback Plan

## Rollback Scope

Revert R17 packaging, contract v4 output lines, capability journal, Phase23 checks, and new plugin runner skill/pipeline.

## Steps

1. Remove packaging file:
   - `pyproject.toml`
2. Revert package loader/version:
   - `prompt-dsl-system/tools/hongzhi_ai_kit/cli.py`
   - `prompt-dsl-system/tools/hongzhi_ai_kit/__init__.py`
3. Revert runner contract changes:
   - `prompt-dsl-system/tools/hongzhi_plugin.py`
4. Revert regression updates:
   - remove Phase23 block from `prompt-dsl-system/tools/golden_path_regression.sh`
5. Remove newly added governance assets:
   - `prompt-dsl-system/05_skill_registry/skills/governance/skill_governance_plugin_runner.yaml`
   - registry entry in `prompt-dsl-system/05_skill_registry/skills.json`
   - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_plugin_discover.md`
6. Revert docs/baselines:
   - `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
   - `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
   - `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`

## Post-Rollback Verification

1. Run validate and regression.
2. Confirm prior expected check counts and plugin behavior.
