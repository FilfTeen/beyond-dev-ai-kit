# Redundancy Report (Aggressive Consolidation)

## Scope and Method
- Source of truth: `prompt-dsl-system/05_skill_registry/skills.json` (28 entries at baseline).
- Verification action: read all 28 referenced YAML files and verify each contains `description`, `output_contract` core keys (`summary/artifacts/risks/next_actions`) and `examples`.
- Consolidation rule: keep one universal execution entry; move all legacy skills out of active registry.

## Grouped Redundancy Analysis

### 1) SQL Group
- Skills:
  - `skill_sql_convert_oracle_to_dm8`
  - `skill_sql_portability_audit`
  - `skill_sql_generate_dm8_ddl_from_schema`
  - `skill_sql_index_review`
  - `skill_sql_data_migration_plan`
- Capability coverage (from descriptions/examples): SQL conversion, portability audit, DDL generation, index review, migration + rollback planning.
- Overlap:
  - all use same artifact handoff contract and stepwise objective pattern;
  - all can be expressed by one task with different objectives and acceptance criteria.
- Super skill mapping:
  - `mode=sql`
  - objective includes refs_hint for legacy intention (audit/convert/index/migration).

### 2) Code Group
- Skills:
  - `skill_code_refactor_java_service`
  - `skill_code_fix_type_mismatch`
  - `skill_code_dependency_trace`
  - `skill_code_generate_change_ledger`
  - `skill_code_security_hardening`
- Capability coverage: dependency tracing, bug fix, refactor, hardening, delivery ledger.
- Overlap:
  - all target module-scoped engineering change workflows and consume previous artifacts.
- Super skill mapping:
  - `mode=code`
  - objective carries refs_hint for trace/fix/hardening/ledger intent.

### 3) Process Group
- Skills:
  - `skill_process_parse_bpmn_to_nodes`
  - `skill_process_state_mapping_audit`
  - `skill_process_generate_test_cases`
- Capability coverage: BPMN parsing, state consistency audit, process test generation.
- Overlap:
  - same pipeline-style inputs and artifact handoff; differs only in sub-goal wording.
- Super skill mapping:
  - `mode=process`
  - objective includes refs_hint for parse/audit/test phase.

### 4) Frontend Group
- Skills:
  - `skill_frontend_trace_page_api_calls`
  - `skill_frontend_fix_layui_form_binding`
  - `skill_frontend_publish_page_online`
- Capability coverage: call graph tracing, form binding fixes, release publish prep.
- Overlap:
  - same module/objective driven execution pattern; differs only in acceptance focus.
- Super skill mapping:
  - `mode=frontend`
  - objective carries refs_hint for trace/fix/publish semantics.

### 5) Release Group
- Skills:
  - `skill_release_build_package_checklist`
  - `skill_release_smoke_test_plan`
  - `skill_release_rollback_plan`
  - `skill_release_db_batch_packaging`
  - `skill_release_db_execution_runbook`
- Capability coverage: release readiness checklist, smoke plan, rollback, DB batch package and runbook.
- Overlap:
  - all are release planning/artifact orchestration tasks under unified output contract.
- Super skill mapping:
  - `mode=release`
  - objective references legacy intent via refs_hint.

### 6) Governance Group
- Skills:
  - `skill_governance_role_project_linkage_audit`
  - `skill_governance_data_boundary_rules`
  - `skill_governance_db_merged_integrity_gate`
  - `skill_governance_read_company_profile`
- Capability coverage: role linkage, data boundary, integrity gate, company profile summarization.
- Overlap:
  - governance checks all follow constraints + risks + next_actions structure.
- Super skill mapping:
  - `mode=governance`
  - objective carries refs_hint for linkage/boundary/gate/profile.

### 7) Docs Group
- Skills:
  - `skill_docs_generate_module_readme`
  - `skill_docs_generate_api_contract`
  - `skill_docs_generate_db_dictionary`
- Capability coverage: module readme, API contract, DB dictionary generation.
- Overlap:
  - all are documentation generation tasks with identical artifact packaging style.
- Super skill mapping:
  - `mode=docs`
  - objective includes refs_hint for doc target type.

## Aggressive Keep List
- Keep in active registry:
  - `skill_hongzhi_universal_ops` (mandatory unified entry)
- Optional system skill:
  - `skill_creator` is not a runtime dependency in current pipelines; not retained in active registry.
- Deprecated:
  - all other legacy skills moved to `prompt-dsl-system/05_skill_registry/deprecated/skills/**`.

## Consolidation Decision
- Active orchestration entry is reduced to one universal skill.
- Pipeline references are unified to one skill and differentiated by `mode + objective + refs_hint`.
- Capability completeness is preserved by objective/constraints/acceptance/forbidden contract and artifact handoff rules.
