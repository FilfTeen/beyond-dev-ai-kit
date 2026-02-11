# A3 Rollback Plan

## Rollback Scope

Revert Round17 packaging + contract v4 + Phase23 additions.

## Steps

1. Remove packaging files:
   - `pyproject.toml`
   - `setup.py`
2. Revert module entry chain:
   - `prompt-dsl-system/tools/hongzhi_ai_kit/cli.py`
   - `prompt-dsl-system/tools/hongzhi_ai_kit/__init__.py`
3. Revert runner contract updates:
   - `prompt-dsl-system/tools/hongzhi_plugin.py`
4. Revert guard noise/packaging allowances:
   - `prompt-dsl-system/tools/path_diff_guard.py`
   - `prompt-dsl-system/tools/guardrails.yaml`
5. Revert skill/pipeline integration:
   - remove `skill_governance_plugin_runner.yaml`
   - remove `pipeline_plugin_discover.md`
   - revert `skills.json`
   - revert `pipeline_module_migration.md`
6. Revert regression/docs/baselines:
   - `prompt-dsl-system/tools/golden_path_regression.sh`
   - `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
   - `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
   - `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`

## Verification After Rollback

- `./prompt-dsl-system/tools/run.sh validate --repo-root .`
- `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
- `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`
