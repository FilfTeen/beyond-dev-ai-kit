# Pipeline: BPMN State Audit + TestGen (Constitution Aligned)

## 输入（必须）
- `allowed_module_root`：允许改动根目录（必填）。
- `objective`：BPMN 路径、变量与状态来源。
- `context_id` / `trace_id` / `input_artifact_refs`。

## 缺失边界时的硬规则
- 若未提供 `allowed_module_root`：第一步仅扫描与风险评估，不得改动。

## Step 1 - BPMN 扫描与影响树（Scan-only）
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；refs_hint: bpmn parse；先扫描并输出影响树与路线A/B。"
  constraints:
    - "scan-only when boundary missing"
  acceptance:
    - "A1 impact tree"
    - "A2 route tradeoff"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测命名/字段/逻辑"
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

## Step 2 - 状态映射审计
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "process"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；refs_hint: state mapping audit；输出状态映射与异常清单。"
  constraints:
    - "facts from bpmn and implementation only"
  acceptance:
    - "A* mapping table"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测命名/字段/逻辑"
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
  input_artifact_refs: ["A1", "A2"]
```

## Step 3 - 测试用例生成
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "process"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；refs_hint: process test generation；生成主路径/异常/边界测试。"
  constraints:
    - "test cases must map to audited states"
  acceptance:
    - "A* test cases"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测命名/字段/逻辑"
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
  input_artifact_refs: ["A2"]
```

## Step 4 - 文档与收尾
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "docs"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；输出 API/DB 文档补充、变更台账、回滚说明、清理报告。"
  constraints:
    - "closure required"
  acceptance:
    - "A* change ledger"
    - "A* rollback plan"
    - "A* cleanup report"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测命名/字段/逻辑"
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
  input_artifact_refs: ["A3"]
```
