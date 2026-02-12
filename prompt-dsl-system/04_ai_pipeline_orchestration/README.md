# AI Pipeline Orchestration (Company Constitution Aligned)

## 总则
- 默认由 `skill_hongzhi_universal_ops` 承载作业能力；治理类 pipeline 允许调用 `skills/governance/*` 下的专用 skill。
- 每步必须包含：`context_id`、`trace_id`、`input_artifact_refs`、`mode`、`objective`、`constraints`、`acceptance`、`forbidden`。
- 每条 pipeline 均要求 `allowed_module_root`；若缺失，第一步只能扫描与风险评估，不得直接改动。
- 默认 forbidden 至少包括：
  - 禁止改 `/sys,/error,/util,/vote`
  - 禁止臆测命名/字段/逻辑

## Pipeline 一览
- `pipeline_sql_oracle_to_dm8.md`
- `pipeline_ownercommittee_audit_fix.md`
- `pipeline_bpmn_state_audit_testgen.md`
- `pipeline_db_delivery_batch_and_runbook.md`
- `pipeline_bugfix_min_scope_with_tree.md`
- `pipeline_skill_creator.md`
- `pipeline_project_bootstrap.md`
- `pipeline_skill_promote.md`
- `pipeline_module_migration.md`
- `pipeline_plugin_discover.md`
- `pipeline_project_stack_bootstrap.md`
- `pipeline_requirement_to_prototype.md`
- `pipeline_kit_self_upgrade.md`

## 运行示例
```bash
./prompt-dsl-system/tools/run.sh run \
  --repo-root . \
  --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_bugfix_min_scope_with_tree.md

# kit 主线升级统一入口
./prompt-dsl-system/tools/run.sh self-upgrade -r .
./prompt-dsl-system/tools/run.sh self-upgrade -r . --strict-self-upgrade
```
