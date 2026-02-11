# A3_R19_rollback_plan

## Rollback Scope
Round19 governance/token/limits/phase25/pipeline-skill changes.

## Steps
1. Revert `prompt-dsl-system/tools/hongzhi_plugin.py` to pre-R19 baseline:
   - remove token TTL/scope logic
   - remove limit exit20 path
   - restore previous capabilities/capabilities.jsonl schema fields
   - restore previous capability_index update payload
2. Revert regression additions in `prompt-dsl-system/tools/golden_path_regression.sh` (Phase25 block).
3. Remove new skill:
   - `prompt-dsl-system/05_skill_registry/skills/governance/skill_governance_plugin_status.yaml`
   - remove entry from `prompt-dsl-system/05_skill_registry/skills.json`
4. Revert pipeline change:
   - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_plugin_discover.md`
5. Revert docs/conventions updates:
   - `PLUGIN_RUNNER.md`
   - `FACT_BASELINE.md`
   - `COMPLIANCE_MATRIX.md`
   - `HONGZHI_COMPANY_CONSTITUTION.md` Rule 19
6. Remove Round19 artifacts:
   - `A1_R19_impact_tree.md`
   - `A2_R19_change_ledger.md`
   - `A3_R19_rollback_plan.md`
   - `A4_R19_cleanup_report.md`
   - `R19_perf_notes.md`
   - `R19_scan_notes.md`

## Post-Rollback Verification
- `./prompt-dsl-system/tools/run.sh validate --repo-root .`
- `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
- `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`
