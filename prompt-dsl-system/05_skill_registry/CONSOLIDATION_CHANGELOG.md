# Consolidation Changelog (Aggressive Merge)

## Added / Modified / Moved Files

### Added
- `prompt-dsl-system/05_skill_registry/BASELINE_REGISTRY_SNAPSHOT.json`
- `prompt-dsl-system/04_ai_pipeline_orchestration/BASELINE_PIPELINE_SNAPSHOT.json`
- `prompt-dsl-system/05_skill_registry/REDUNDANCY_REPORT.md`
- `prompt-dsl-system/05_skill_registry/skills/universal/skill_hongzhi_universal_ops.yaml`
- `prompt-dsl-system/tools/run_plan_sql.yaml`
- `prompt-dsl-system/tools/run_plan_ownercommittee.yaml`
- `prompt-dsl-system/tools/run_plan_bpmn.yaml`

### Modified
- `prompt-dsl-system/05_skill_registry/skills.json` (active registry shrunk to single universal skill)
- `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md`
- `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_ownercommittee_audit_fix.md`
- `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_bpmn_state_audit_testgen.md`
- `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_db_delivery_batch_and_runbook.md`
- `prompt-dsl-system/04_ai_pipeline_orchestration/README.md`
- `prompt-dsl-system/tools/validate_report.json`
- `prompt-dsl-system/tools/run_plan.yaml`

### Moved (to deprecated)
- `28` legacy skills moved from `prompt-dsl-system/05_skill_registry/skills/**` to `prompt-dsl-system/05_skill_registry/deprecated/skills/**`.

## Deprecated Archive List

| Old Skill | Deprecated Path | Suggested Mode |
|---|---|---|
| `skill_code_dependency_trace` | `prompt-dsl-system/05_skill_registry/deprecated/skills/code/skill_code_dependency_trace.yaml` | `code` |
| `skill_code_fix_type_mismatch` | `prompt-dsl-system/05_skill_registry/deprecated/skills/code/skill_code_fix_type_mismatch.yaml` | `code` |
| `skill_code_generate_change_ledger` | `prompt-dsl-system/05_skill_registry/deprecated/skills/code/skill_code_generate_change_ledger.yaml` | `code` |
| `skill_code_refactor_java_service` | `prompt-dsl-system/05_skill_registry/deprecated/skills/code/skill_code_refactor_java_service.yaml` | `code` |
| `skill_code_security_hardening` | `prompt-dsl-system/05_skill_registry/deprecated/skills/code/skill_code_security_hardening.yaml` | `code` |
| `skill_docs_generate_api_contract` | `prompt-dsl-system/05_skill_registry/deprecated/skills/docs/skill_docs_generate_api_contract.yaml` | `docs` |
| `skill_docs_generate_db_dictionary` | `prompt-dsl-system/05_skill_registry/deprecated/skills/docs/skill_docs_generate_db_dictionary.yaml` | `docs` |
| `skill_docs_generate_module_readme` | `prompt-dsl-system/05_skill_registry/deprecated/skills/docs/skill_docs_generate_module_readme.yaml` | `docs` |
| `skill_frontend_fix_layui_form_binding` | `prompt-dsl-system/05_skill_registry/deprecated/skills/frontend/skill_frontend_fix_layui_form_binding.yaml` | `frontend` |
| `skill_frontend_publish_page_online` | `prompt-dsl-system/05_skill_registry/deprecated/skills/frontend/skill_frontend_publish_page_online.yaml` | `frontend` |
| `skill_frontend_trace_page_api_calls` | `prompt-dsl-system/05_skill_registry/deprecated/skills/frontend/skill_frontend_trace_page_api_calls.yaml` | `frontend` |
| `skill_governance_data_boundary_rules` | `prompt-dsl-system/05_skill_registry/deprecated/skills/governance/skill_governance_data_boundary_rules.yaml` | `governance` |
| `skill_governance_db_merged_integrity_gate` | `prompt-dsl-system/05_skill_registry/deprecated/skills/governance/skill_governance_db_merged_integrity_gate.yaml` | `governance` |
| `skill_governance_read_company_profile` | `prompt-dsl-system/05_skill_registry/deprecated/skills/governance/skill_governance_read_company_profile.yaml` | `governance` |
| `skill_governance_role_project_linkage_audit` | `prompt-dsl-system/05_skill_registry/deprecated/skills/governance/skill_governance_role_project_linkage_audit.yaml` | `governance` |
| `skill_process_generate_test_cases` | `prompt-dsl-system/05_skill_registry/deprecated/skills/process/skill_process_generate_test_cases.yaml` | `process` |
| `skill_process_parse_bpmn_to_nodes` | `prompt-dsl-system/05_skill_registry/deprecated/skills/process/skill_process_parse_bpmn_to_nodes.yaml` | `process` |
| `skill_process_state_mapping_audit` | `prompt-dsl-system/05_skill_registry/deprecated/skills/process/skill_process_state_mapping_audit.yaml` | `process` |
| `skill_release_build_package_checklist` | `prompt-dsl-system/05_skill_registry/deprecated/skills/release/skill_release_build_package_checklist.yaml` | `release` |
| `skill_release_db_batch_packaging` | `prompt-dsl-system/05_skill_registry/deprecated/skills/release/skill_release_db_batch_packaging.yaml` | `release` |
| `skill_release_db_execution_runbook` | `prompt-dsl-system/05_skill_registry/deprecated/skills/release/skill_release_db_execution_runbook.yaml` | `release` |
| `skill_release_rollback_plan` | `prompt-dsl-system/05_skill_registry/deprecated/skills/release/skill_release_rollback_plan.yaml` | `release` |
| `skill_release_smoke_test_plan` | `prompt-dsl-system/05_skill_registry/deprecated/skills/release/skill_release_smoke_test_plan.yaml` | `release` |
| `skill_sql_convert_oracle_to_dm8` | `prompt-dsl-system/05_skill_registry/deprecated/skills/sql/skill_sql_convert_oracle_to_dm8.yaml` | `sql` |
| `skill_sql_data_migration_plan` | `prompt-dsl-system/05_skill_registry/deprecated/skills/sql/skill_sql_data_migration_plan.yaml` | `sql` |
| `skill_sql_generate_dm8_ddl_from_schema` | `prompt-dsl-system/05_skill_registry/deprecated/skills/sql/skill_sql_generate_dm8_ddl_from_schema.yaml` | `sql` |
| `skill_sql_index_review` | `prompt-dsl-system/05_skill_registry/deprecated/skills/sql/skill_sql_index_review.yaml` | `sql` |
| `skill_sql_portability_audit` | `prompt-dsl-system/05_skill_registry/deprecated/skills/sql/skill_sql_portability_audit.yaml` | `sql` |

## Pipeline Change Summary

| Pipeline | Baseline Steps (skills) | New Steps (skills) |
|---|---|---|
| `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_bpmn_state_audit_testgen.md` | skill_process_parse_bpmn_to_nodes, skill_process_state_mapping_audit, skill_process_generate_test_cases, skill_docs_generate_api_contract, skill_docs_generate_db_dictionary | skill_hongzhi_universal_ops, skill_hongzhi_universal_ops, skill_hongzhi_universal_ops, skill_hongzhi_universal_ops, skill_hongzhi_universal_ops |
| `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_db_delivery_batch_and_runbook.md` | skill_release_db_batch_packaging, skill_governance_db_merged_integrity_gate, skill_release_db_execution_runbook | skill_hongzhi_universal_ops, skill_hongzhi_universal_ops, skill_hongzhi_universal_ops |
| `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_ownercommittee_audit_fix.md` | skill_code_dependency_trace, skill_code_fix_type_mismatch, skill_code_security_hardening, skill_code_generate_change_ledger, skill_docs_generate_module_readme | skill_hongzhi_universal_ops, skill_hongzhi_universal_ops, skill_hongzhi_universal_ops, skill_hongzhi_universal_ops, skill_hongzhi_universal_ops |
| `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md` | skill_sql_portability_audit, skill_sql_convert_oracle_to_dm8, skill_sql_index_review, skill_sql_data_migration_plan | skill_hongzhi_universal_ops, skill_hongzhi_universal_ops, skill_hongzhi_universal_ops, skill_hongzhi_universal_ops |

## Acceptance Results

- Validate: `./prompt-dsl-system/tools/run.sh validate --repo-root .` -> `Errors=0`, `Warnings=0`.
- Run checks:
  - `pipeline_sql_oracle_to_dm8.md` -> `prompt-dsl-system/tools/run_plan_sql.yaml`: steps=4, all_steps_universal=true, has_context_trace_input_refs_per_step=true
  - `pipeline_ownercommittee_audit_fix.md` -> `prompt-dsl-system/tools/run_plan_ownercommittee.yaml`: steps=5, all_steps_universal=true, has_context_trace_input_refs_per_step=true
  - `pipeline_bpmn_state_audit_testgen.md` -> `prompt-dsl-system/tools/run_plan_bpmn.yaml`: steps=5, all_steps_universal=true, has_context_trace_input_refs_per_step=true

## Rollback Guide

- Restore registry from baseline snapshot: read `prompt-dsl-system/05_skill_registry/BASELINE_REGISTRY_SNAPSHOT.json` and write `skills_json_backup` back to `prompt-dsl-system/05_skill_registry/skills.json`.
- Restore pipelines from baseline snapshot: read `prompt-dsl-system/04_ai_pipeline_orchestration/BASELINE_PIPELINE_SNAPSHOT.json` and write each `content_backup` back to its `pipeline` path.
- Move archived skills back: copy files from `prompt-dsl-system/05_skill_registry/deprecated/skills/<domain>/*.yaml` to `prompt-dsl-system/05_skill_registry/skills/<domain>/` and remove the three-line deprecation header if needed.
- Re-run validation: `./prompt-dsl-system/tools/run.sh validate --repo-root .`.
