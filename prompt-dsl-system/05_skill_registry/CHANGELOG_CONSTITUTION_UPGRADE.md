# Changelog: Constitution Upgrade

## Scope
- Only `prompt-dsl-system/**` was changed.

## Added Files
- `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
- `prompt-dsl-system/00_conventions/HONGZHI_COMPANY_CONSTITUTION.md`
- `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`
- `prompt-dsl-system/00_conventions/ROLLBACK_INSTRUCTIONS.md`
- `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_bugfix_min_scope_with_tree.md`
- `prompt-dsl-system/tools/ops_guard.py`
- `prompt-dsl-system/tools/ops_guard_report.json`
- `prompt-dsl-system/tools/run_plan_bugfix.yaml`

## Modified Files
- `prompt-dsl-system/00_conventions/SKILL_SPEC.md`
- `prompt-dsl-system/04_ai_pipeline_orchestration/README.md`
- `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md`
- `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_ownercommittee_audit_fix.md`
- `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_bpmn_state_audit_testgen.md`
- `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_db_delivery_batch_and_runbook.md`
- `prompt-dsl-system/05_skill_registry/skills/universal/skill_hongzhi_universal_ops.yaml`
- `prompt-dsl-system/05_skill_registry/deprecated/skills/** (headers updated with mapping hints)`
- `prompt-dsl-system/tools/README.md`
- `prompt-dsl-system/tools/validate_report.json`
- `prompt-dsl-system/tools/run_plan.yaml`
- `prompt-dsl-system/tools/run_plan_sql.yaml`
- `prompt-dsl-system/tools/run_plan_ownercommittee.yaml`
- `prompt-dsl-system/tools/run_plan_bpmn.yaml`

## Deprecated Skills (archived, not deleted)
- Total archived skills: `28`

| Old Skill | Deprecated Path | Suggested Mode | Mapping Hints |
|---|---|---|---|
| `skill_code_dependency_trace` | `prompt-dsl-system/05_skill_registry/deprecated/skills/code/skill_code_dependency_trace.yaml` | `code` | `Use mode=code; put refs_hint=skill_code_dependency_trace in objective/constraints; preserve legacy acceptance checks.` |
| `skill_code_fix_type_mismatch` | `prompt-dsl-system/05_skill_registry/deprecated/skills/code/skill_code_fix_type_mismatch.yaml` | `code` | `Use mode=code; put refs_hint=skill_code_fix_type_mismatch in objective/constraints; preserve legacy acceptance checks.` |
| `skill_code_generate_change_ledger` | `prompt-dsl-system/05_skill_registry/deprecated/skills/code/skill_code_generate_change_ledger.yaml` | `code` | `Use mode=code; put refs_hint=skill_code_generate_change_ledger in objective/constraints; preserve legacy acceptance checks.` |
| `skill_code_refactor_java_service` | `prompt-dsl-system/05_skill_registry/deprecated/skills/code/skill_code_refactor_java_service.yaml` | `code` | `Use mode=code; put refs_hint=skill_code_refactor_java_service in objective/constraints; preserve legacy acceptance checks.` |
| `skill_code_security_hardening` | `prompt-dsl-system/05_skill_registry/deprecated/skills/code/skill_code_security_hardening.yaml` | `code` | `Use mode=code; put refs_hint=skill_code_security_hardening in objective/constraints; preserve legacy acceptance checks.` |
| `skill_docs_generate_api_contract` | `prompt-dsl-system/05_skill_registry/deprecated/skills/docs/skill_docs_generate_api_contract.yaml` | `docs` | `Use mode=docs; put refs_hint=skill_docs_generate_api_contract in objective/constraints; preserve legacy acceptance checks.` |
| `skill_docs_generate_db_dictionary` | `prompt-dsl-system/05_skill_registry/deprecated/skills/docs/skill_docs_generate_db_dictionary.yaml` | `docs` | `Use mode=docs; put refs_hint=skill_docs_generate_db_dictionary in objective/constraints; preserve legacy acceptance checks.` |
| `skill_docs_generate_module_readme` | `prompt-dsl-system/05_skill_registry/deprecated/skills/docs/skill_docs_generate_module_readme.yaml` | `docs` | `Use mode=docs; put refs_hint=skill_docs_generate_module_readme in objective/constraints; preserve legacy acceptance checks.` |
| `skill_frontend_fix_layui_form_binding` | `prompt-dsl-system/05_skill_registry/deprecated/skills/frontend/skill_frontend_fix_layui_form_binding.yaml` | `frontend` | `Use mode=frontend; put refs_hint=skill_frontend_fix_layui_form_binding in objective/constraints; preserve legacy acceptance checks.` |
| `skill_frontend_publish_page_online` | `prompt-dsl-system/05_skill_registry/deprecated/skills/frontend/skill_frontend_publish_page_online.yaml` | `frontend` | `Use mode=frontend; put refs_hint=skill_frontend_publish_page_online in objective/constraints; preserve legacy acceptance checks.` |
| `skill_frontend_trace_page_api_calls` | `prompt-dsl-system/05_skill_registry/deprecated/skills/frontend/skill_frontend_trace_page_api_calls.yaml` | `frontend` | `Use mode=frontend; put refs_hint=skill_frontend_trace_page_api_calls in objective/constraints; preserve legacy acceptance checks.` |
| `skill_governance_data_boundary_rules` | `prompt-dsl-system/05_skill_registry/deprecated/skills/governance/skill_governance_data_boundary_rules.yaml` | `governance` | `Use mode=governance; put refs_hint=skill_governance_data_boundary_rules in objective/constraints; preserve legacy acceptance checks.` |
| `skill_governance_db_merged_integrity_gate` | `prompt-dsl-system/05_skill_registry/deprecated/skills/governance/skill_governance_db_merged_integrity_gate.yaml` | `governance` | `Use mode=governance; put refs_hint=skill_governance_db_merged_integrity_gate in objective/constraints; preserve legacy acceptance checks.` |
| `skill_governance_read_company_profile` | `prompt-dsl-system/05_skill_registry/deprecated/skills/governance/skill_governance_read_company_profile.yaml` | `governance` | `Use mode=governance; put refs_hint=skill_governance_read_company_profile in objective/constraints; preserve legacy acceptance checks.` |
| `skill_governance_role_project_linkage_audit` | `prompt-dsl-system/05_skill_registry/deprecated/skills/governance/skill_governance_role_project_linkage_audit.yaml` | `governance` | `Use mode=governance; put refs_hint=skill_governance_role_project_linkage_audit in objective/constraints; preserve legacy acceptance checks.` |
| `skill_process_generate_test_cases` | `prompt-dsl-system/05_skill_registry/deprecated/skills/process/skill_process_generate_test_cases.yaml` | `process` | `Use mode=process; put refs_hint=skill_process_generate_test_cases in objective/constraints; preserve legacy acceptance checks.` |
| `skill_process_parse_bpmn_to_nodes` | `prompt-dsl-system/05_skill_registry/deprecated/skills/process/skill_process_parse_bpmn_to_nodes.yaml` | `process` | `Use mode=process; put refs_hint=skill_process_parse_bpmn_to_nodes in objective/constraints; preserve legacy acceptance checks.` |
| `skill_process_state_mapping_audit` | `prompt-dsl-system/05_skill_registry/deprecated/skills/process/skill_process_state_mapping_audit.yaml` | `process` | `Use mode=process; put refs_hint=skill_process_state_mapping_audit in objective/constraints; preserve legacy acceptance checks.` |
| `skill_release_build_package_checklist` | `prompt-dsl-system/05_skill_registry/deprecated/skills/release/skill_release_build_package_checklist.yaml` | `release` | `Use mode=release; put refs_hint=skill_release_build_package_checklist in objective/constraints; preserve legacy acceptance checks.` |
| `skill_release_db_batch_packaging` | `prompt-dsl-system/05_skill_registry/deprecated/skills/release/skill_release_db_batch_packaging.yaml` | `release` | `Use mode=release; put refs_hint=skill_release_db_batch_packaging in objective/constraints; preserve legacy acceptance checks.` |
| `skill_release_db_execution_runbook` | `prompt-dsl-system/05_skill_registry/deprecated/skills/release/skill_release_db_execution_runbook.yaml` | `release` | `Use mode=release; put refs_hint=skill_release_db_execution_runbook in objective/constraints; preserve legacy acceptance checks.` |
| `skill_release_rollback_plan` | `prompt-dsl-system/05_skill_registry/deprecated/skills/release/skill_release_rollback_plan.yaml` | `release` | `Use mode=release; put refs_hint=skill_release_rollback_plan in objective/constraints; preserve legacy acceptance checks.` |
| `skill_release_smoke_test_plan` | `prompt-dsl-system/05_skill_registry/deprecated/skills/release/skill_release_smoke_test_plan.yaml` | `release` | `Use mode=release; put refs_hint=skill_release_smoke_test_plan in objective/constraints; preserve legacy acceptance checks.` |
| `skill_sql_convert_oracle_to_dm8` | `prompt-dsl-system/05_skill_registry/deprecated/skills/sql/skill_sql_convert_oracle_to_dm8.yaml` | `sql` | `Use mode=sql; put refs_hint=skill_sql_convert_oracle_to_dm8 in objective/constraints; preserve legacy acceptance checks.` |
| `skill_sql_data_migration_plan` | `prompt-dsl-system/05_skill_registry/deprecated/skills/sql/skill_sql_data_migration_plan.yaml` | `sql` | `Use mode=sql; put refs_hint=skill_sql_data_migration_plan in objective/constraints; preserve legacy acceptance checks.` |
| `skill_sql_generate_dm8_ddl_from_schema` | `prompt-dsl-system/05_skill_registry/deprecated/skills/sql/skill_sql_generate_dm8_ddl_from_schema.yaml` | `sql` | `Use mode=sql; put refs_hint=skill_sql_generate_dm8_ddl_from_schema in objective/constraints; preserve legacy acceptance checks.` |
| `skill_sql_index_review` | `prompt-dsl-system/05_skill_registry/deprecated/skills/sql/skill_sql_index_review.yaml` | `sql` | `Use mode=sql; put refs_hint=skill_sql_index_review in objective/constraints; preserve legacy acceptance checks.` |
| `skill_sql_portability_audit` | `prompt-dsl-system/05_skill_registry/deprecated/skills/sql/skill_sql_portability_audit.yaml` | `sql` | `Use mode=sql; put refs_hint=skill_sql_portability_audit in objective/constraints; preserve legacy acceptance checks.` |

## Acceptance Evidence
- Validate: `Errors=0`, `Warnings=0`
- Run plans generated successfully for:
  - `pipeline_sql_oracle_to_dm8.md`
  - `pipeline_ownercommittee_audit_fix.md`
  - `pipeline_bpmn_state_audit_testgen.md`
  - `pipeline_bugfix_min_scope_with_tree.md`
- All steps in generated run plans reference `skill_hongzhi_universal_ops`.

## Rollback Method
- Follow `prompt-dsl-system/00_conventions/ROLLBACK_INSTRUCTIONS.md`.
- Baseline restoration sources:
  - `prompt-dsl-system/05_skill_registry/BASELINE_REGISTRY_SNAPSHOT.json`
  - `prompt-dsl-system/04_ai_pipeline_orchestration/BASELINE_PIPELINE_SNAPSHOT.json`
