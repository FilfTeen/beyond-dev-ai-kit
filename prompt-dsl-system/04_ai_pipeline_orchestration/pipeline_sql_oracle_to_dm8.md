# Pipeline: SQL Oracle -> DM8 (Constitution Aligned)

## 适用场景
- Oracle SQL 迁移到 DM8，优先可移植 SQL。

## 输入（必须）
- `allowed_module_root`：允许改动的模块根路径（必填）。
- `objective`：输入、约束、验收、禁止项。
- `context_id` / `trace_id` / `input_artifact_refs`。

## 缺失边界时的硬规则
- 若未提供 `allowed_module_root`：第一步只能执行扫描与风险评估，不得直接改动。

## Step 1 - 扫描与影响树（Scan-only）
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；refs_hint: sql portability audit；先扫描并输出影响树与路线A/B。"
  constraints:
    - "if allowed_module_root is missing, scan-only"
    - "dependency order: compat > self-contained > minimal-invasive"
  acceptance:
    - "A1 impact tree"
    - "A2 route A/B tradeoff"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测命名/字段/逻辑"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    forbidden_paths:
      - "/sys"
      - "/error"
      - "/util"
      - "/vote"
    max_change_scope: "minimal"
  fact_policy:
    require_scan_before_change: true
    unknown_requires_user: true
  self_monitor_policy:
    loop_detection: true
    auto_rollback_on_loop: true
  decision_policy:
    dependency_strategy_order:
      - "compat"
      - "self-contained"
      - "minimal-invasive"
    choose_best_route_with_tradeoff: true
  sql_policy:
    prefer_portable_sql: true
    dual_sql_when_needed:
      - "oracle"
      - "mysql"
  target_db: "dm8"
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: []
```

## Step 2 - Oracle->DM8 转换
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "sql"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；refs_hint: skill_sql_convert_oracle_to_dm8；执行可移植优先转换。"
  constraints:
    - "portable SQL first"
    - "when not portable, produce oracle/mysql dual sql"
  acceptance:
    - "A* converted sql"
    - "A* change ledger"
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
  target_db: "dm8"
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: ["A1", "A2"]
```

## Step 3 - 索引与迁移策略
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "sql"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；refs_hint: index review + migration plan；输出索引建议与迁移批次。"
  constraints:
    - "minimal-invasive changes"
  acceptance:
    - "A* rollback plan"
    - "A* migration notes"
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
  target_db: "dm8"
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: ["A2"]
```

## Step 4 - 收尾文档与清理
```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "docs"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；输出作业日志、回滚说明、清理报告。"
  constraints:
    - "closure required"
  acceptance:
    - "A* impact tree"
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
