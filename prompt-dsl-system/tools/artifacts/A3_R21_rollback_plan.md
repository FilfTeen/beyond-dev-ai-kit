# A3_R21_rollback_plan

## Rollback Objective
Revert Round21 features (Hint Loop + Layout Adapters + Phase27 + skill/pipeline additions) with minimal blast radius.

## Rollback Steps
1. Remove Round21 new files:
   - `prompt-dsl-system/tools/layout_adapters.py`
   - `prompt-dsl-system/05_skill_registry/skills/governance/skill_governance_plugin_discover_with_hints.yaml`
   - `prompt-dsl-system/tools/_tmp_structure_cases/case6_maven_multi_module/**`
   - `prompt-dsl-system/tools/_tmp_structure_cases/case7_nonstandard_java_root/**`
   - `prompt-dsl-system/tools/artifacts/A1_R21_impact_tree.md`
   - `prompt-dsl-system/tools/artifacts/A2_R21_change_ledger.md`
   - `prompt-dsl-system/tools/artifacts/A3_R21_rollback_plan.md`
   - `prompt-dsl-system/tools/artifacts/A4_R21_cleanup_report.md`
2. Revert edits in:
   - `prompt-dsl-system/tools/hongzhi_plugin.py`
   - `prompt-dsl-system/tools/golden_path_regression.sh` (drop Phase27 block)
   - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_plugin_discover.md`
   - `prompt-dsl-system/05_skill_registry/skills.json`
   - `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
   - `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
   - `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`
3. Re-run gates:
   - `./prompt-dsl-system/tools/run.sh validate --repo-root .`
   - `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
   - `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`
4. Confirm baseline returns to pre-Round21 total checks and all PASS.

## Safety Notes
- Governance block path remains authoritative in both pre/post rollback states.
- Rollback does not require any writes to external target repos.
