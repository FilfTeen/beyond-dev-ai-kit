# Pipeline: DB Delivery Batch + Gate + Runbook (Constitution Aligned)

## 输入（必须）
- `allowed_module_root`：允许改动根目录（必填）。
- `objective`：输入、约束、验收、禁止项。
- `target_db`：`oracle|dm8|mysql`。
- `context_id` / `trace_id` / `input_artifact_refs`。

## 缺失边界时的硬规则
- 若未提供 `allowed_module_root`：第一步仅扫描与风险评估，不得改动。

## Step 1 - 批次打包策略（Scan-first）
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "release"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；refs_hint: db batch packaging；规划 Batch0~BatchN 与影响树。"
  constraints:
    - "scan evidence first"
    - "if boundary missing then no direct edits"
  acceptance:
    - "A* impact tree"
    - "A* batch packaging plan"
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
  target_db: "{{target_db}}"
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: []
```

## Step 2 - 完整性闸门
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；refs_hint: merged integrity gate；生成发布前闸门规则和命令模板。"
  constraints:
    - "must consume Step1 artifacts"
  acceptance:
    - "A* gate checklist"
    - "A* ruleset"
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

## Step 3 - 执行 Runbook + 回滚
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "release"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；refs_hint: execution runbook；产出 Fresh/Incremental runbook 与 fail-fast rollback。"
  constraints:
    - "operator-ready"
  acceptance:
    - "A* runbook"
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
  target_db: "{{target_db}}"
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: ["A2", "A3"]
```
