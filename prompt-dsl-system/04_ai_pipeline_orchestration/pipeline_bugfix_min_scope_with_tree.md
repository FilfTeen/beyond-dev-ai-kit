# Pipeline: Bugfix Min Scope With Tree (Company Generic)

## 适用场景
- 模糊指令/症状类 bug 修复，要求最小改动、树状分析、自监控和可回滚。

## 输入（必须）
- `allowed_module_root`：允许改动根目录（必填）。
- `objective`：问题现象、复现路径、约束、验收。
- `context_id` / `trace_id` / `input_artifact_refs`。

## 缺失边界时的硬规则
- 若未提供 `allowed_module_root`：第一步仅扫描与风险评估，不得改动。

## Step 1 - 扫描 + 影响树 + 路线A/B（不改代码）
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；先扫描，输出影响树和路线A/B（compat/self-contained/minimal-invasive）。"
  constraints:
    - "scan-only"
    - "decision order: compat > self-contained > minimal-invasive"
  acceptance:
    - "A* impact tree"
    - "A* route comparison"
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

## Step 2 - 最小补丁（仅 allowed-root）
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "code"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；按 Step1 选择的最优路线执行最小侵入补丁。"
  constraints:
    - "only inside allowed_module_root"
    - "loop signal => rollback first"
  acceptance:
    - "A* patch ledger"
    - "A* rollback trigger"
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

## Step 3 - Smoke Checklist + Rollback Plan
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "release"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；生成 smoke checklist 与 fail-fast rollback plan。"
  constraints:
    - "release safety first"
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
  input_artifact_refs: ["A2"]
```

## Step 4 - README 更新 + Change Ledger + Cleanup
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "docs"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；更新模块 README 与收尾文档（change ledger/cleanup）。"
  constraints:
    - "closure mandatory"
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
  input_artifact_refs: ["A3"]
```
