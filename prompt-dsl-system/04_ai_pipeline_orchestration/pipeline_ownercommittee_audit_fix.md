# Pipeline: OwnerCommittee Audit + Fix (Constitution Aligned)

## 输入（必须）
- `allowed_module_root`：允许改动根目录（必填）。
- `objective`：问题复现、影响面、约束、验收。
- `context_id` / `trace_id` / `input_artifact_refs`。

## 缺失边界时的硬规则
- 若未提供 `allowed_module_root`：第一步仅扫描与风险评估，不得改动。

## Step 1 - 扫描、影响树、路线 A/B（Scan-only）
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；refs_hint: dependency trace；输出影响树与路线A/B。"
  constraints:
    - "scan-only when boundary missing"
    - "dependency order: compat > self-contained > minimal-invasive"
  acceptance:
    - "A1 impact tree"
    - "A2 route A/B"
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

## Step 2 - 最小补丁修复
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "code"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；refs_hint: type mismatch fix；仅做最小补丁。"
  constraints:
    - "minimal change scope"
  acceptance:
    - "A* patch + checks"
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

## Step 3 - 安全加固 + 自监控
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "code"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；refs_hint: security hardening；执行模块内加固并检查回圈风险。"
  constraints:
    - "loop signal => rollback first"
  acceptance:
    - "A* hardening notes"
    - "A* rollback triggers"
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

## Step 4 - 发布前检查
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "release"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；生成 smoke checklist 与回滚计划。"
  constraints:
    - "fail-fast checkpoints required"
  acceptance:
    - "A* smoke checklist"
    - "A* rollback plan"
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

## Step 5 - 文档收尾
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "docs"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；更新模块 README、变更台账、清理报告。"
  constraints:
    - "closure pack required"
  acceptance:
    - "A* change ledger"
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
  input_artifact_refs: ["A4"]
```
