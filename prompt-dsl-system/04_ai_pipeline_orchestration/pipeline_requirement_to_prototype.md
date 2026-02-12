# Pipeline: Requirement To Prototype (产品经理链路)

## 适用场景

- 用户给出标书/需求描述，但信息还不完整，需要先结构化澄清。
- 在开发前先产出业务流程、功能清单、验收标准和低保真原型说明。
- 作为后续模块开发 pipeline 的输入基线。

## 输入（必须）

- `allowed_module_root`：必须为 `prompt-dsl-system`。
- `requirement_input`：需求文本、标书摘要、会议纪要或客户反馈。
- `project_key` / `module_key`（可选，但建议提供）。
- `context_id` / `trace_id` / `input_artifact_refs`。

## Step 1 — 需求澄清与事实边界

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "将 requirement_input 结构化为：目标、角色、范围、约束、风险和待确认问题；先输出事实与未知边界，禁止直接进入方案实现。"
  constraints:
    - "scan-only"
    - "unknown facts must go to required_additional_information checklist"
    - "must include in-scope/out-of-scope boundaries"
  acceptance:
    - "A1_requirement_baseline.md"
    - "A1_required_additional_information.md"
    - "A1_impact_tree.md"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测业务规则"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    forbidden_paths: ["/sys", "/error", "/util", "/vote"]
    max_change_scope: "minimal"
  fact_policy: {require_scan_before_change: true, unknown_requires_user: true}
  self_monitor_policy: {loop_detection: true, auto_rollback_on_loop: true}
  decision_policy: {dependency_strategy_order: ["compat", "self-contained", "minimal-invasive"], choose_best_route_with_tradeoff: true}
  sql_policy: {prefer_portable_sql: true, dual_sql_when_needed: ["oracle", "mysql"]}
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: []
```

## Step 2 — 业务流程与功能切片设计

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "process"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "基于 A1 输出业务流程图文本版（含状态与分支）、角色权限矩阵、功能切片（MVP/增强项）、异常路径和数据流。"
  constraints:
    - "flow must include precondition/event/action/result"
    - "must mark activiti touch points if workflow exists"
    - "must include rollback-safe fallback paths"
  acceptance:
    - "A2_process_flow.md"
    - "A2_feature_slices.md"
    - "A2_role_matrix.md"
  forbidden:
    - "禁止跳过异常路径分析"
    - "禁止跨模块越界定义职责"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    forbidden_paths: ["/sys", "/error", "/util", "/vote"]
    max_change_scope: "minimal"
  fact_policy: {require_scan_before_change: true, unknown_requires_user: true}
  self_monitor_policy: {loop_detection: true, auto_rollback_on_loop: true}
  decision_policy: {dependency_strategy_order: ["compat", "self-contained", "minimal-invasive"], choose_best_route_with_tradeoff: true}
  sql_policy: {prefer_portable_sql: true, dual_sql_when_needed: ["oracle", "mysql"]}
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: ["A1_requirement_baseline.md"]
```

## Step 3 — 接口/数据/验收与低保真原型

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "docs"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "输出开发可执行说明：API 草案、数据实体草案、验收标准（Given-When-Then）、页面原型说明（页面块+交互状态+字段）。"
  constraints:
    - "api paths should follow existing module style"
    - "sql and db notes must keep oracle/mysql compatibility awareness"
    - "prototype should be low-fidelity text spec (not final visual design)"
  acceptance:
    - "A3_api_contract_draft.md"
    - "A3_data_model_draft.md"
    - "A3_acceptance_criteria.md"
    - "A3_low_fidelity_prototype.md"
  forbidden:
    - "禁止虚构不存在的系统资产"
    - "禁止给出不可落地的技术路线"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    forbidden_paths: ["/sys", "/error", "/util", "/vote"]
    max_change_scope: "minimal"
  fact_policy: {require_scan_before_change: true, unknown_requires_user: true}
  self_monitor_policy: {loop_detection: true, auto_rollback_on_loop: true}
  decision_policy: {dependency_strategy_order: ["compat", "self-contained", "minimal-invasive"], choose_best_route_with_tradeoff: true}
  sql_policy: {prefer_portable_sql: true, dual_sql_when_needed: ["oracle", "mysql"]}
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: ["A2_process_flow.md", "A2_feature_slices.md"]
```

## Step 4 — 收尾文档与作业日志

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "docs"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "生成收尾包（变更台账、回退计划、清理报告、下一步开发建议），并更新相关 README/目录说明。"
  constraints:
    - "closure mandatory"
    - "if no cleanup: cleanup report must explicitly state none"
  acceptance:
    - "A4_change_ledger.md"
    - "A5_rollback_plan.md"
    - "A6_cleanup_report.md"
    - "A7_next_step_recommendations.md"
  forbidden:
    - "禁止遗漏回退方案"
    - "禁止越界改动业务代码"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    forbidden_paths: ["/sys", "/error", "/util", "/vote"]
    max_change_scope: "minimal"
  fact_policy: {require_scan_before_change: true, unknown_requires_user: true}
  self_monitor_policy: {loop_detection: true, auto_rollback_on_loop: true}
  decision_policy: {dependency_strategy_order: ["compat", "self-contained", "minimal-invasive"], choose_best_route_with_tradeoff: true}
  sql_policy: {prefer_portable_sql: true, dual_sql_when_needed: ["oracle", "mysql"]}
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: ["A3_api_contract_draft.md", "A3_low_fidelity_prototype.md"]
```
