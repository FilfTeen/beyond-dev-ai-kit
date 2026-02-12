# Pipeline: Project Stack Bootstrap (Tech Stack KB 建档)

## 适用场景

- 新项目接入时，先建立项目技术栈知识库，避免后续 skill/pipeline 依赖猜测。
- 对已有项目做周期性技术栈盘点（框架、数据库、构建工具、流程引擎、VCS）。
- 为跨项目模块迁移提供事实基线。

## 输入（必须）

- `allowed_module_root`：必须为 `prompt-dsl-system`。
- `project_key`：项目标识（如 `xywygl`）。
- `target_repo_root`：待扫描项目的仓库根路径（绝对路径）。
- `context_id` / `trace_id` / `input_artifact_refs`。

## Step 1 — 扫描计划 + 影响树（不改业务仓库）

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "确认扫描边界与风险：仅允许读取 {{target_repo_root}}，仅允许写 prompt-dsl-system/project_stacks/{{project_key}}/*；输出影响树与扫描计划。"
  constraints:
    - "scan-only"
    - "target repo read-only"
    - "no write outside prompt-dsl-system/project_stacks"
  acceptance:
    - "A1_impact_tree.md"
    - "A1_stack_scan_plan.md"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止修改目标业务仓库"
    - "禁止臆测技术栈"
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

## Step 2 — 执行技术栈扫描并生成 discovered profile

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "执行 project_stack_scanner.py 扫描 {{target_repo_root}} 并生成 prompt-dsl-system/project_stacks/{{project_key}}/stack_profile.discovered.yaml。"
  constraints:
    - "scanner command: /usr/bin/python3 prompt-dsl-system/tools/project_stack_scanner.py --repo-root {{target_repo_root}} --project-key {{project_key}} --kit-root ."
    - "must include scanner evidence list"
    - "must not write any file under target repo"
  acceptance:
    - "A2_stack_profile_discovered.yaml"
    - "A2_stack_scan_evidence.md"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止修改目标业务仓库"
    - "禁止臆测技术栈"
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
  input_artifact_refs: ["A1_impact_tree.md"]
```

## Step 3 — 声明档案对齐 + 缺口清单

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "docs"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "对齐 declared/discovered stack profile，输出差异与补录事项。若 declared 不存在则从模板生成 declared 初稿。"
  constraints:
    - "declared path: prompt-dsl-system/project_stacks/{{project_key}}/stack_profile.yaml"
    - "if declared missing: create from template and mark confidence=low"
    - "must produce reconciliation notes when conflicts exist"
  acceptance:
    - "A3_stack_profile_diff.md"
    - "A3_required_additional_information.md"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止改动目标业务仓库"
    - "禁止无证据覆盖已有声明"
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
  input_artifact_refs: ["A2_stack_profile_discovered.yaml"]
```

## Step 4 — 收尾与校验

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "docs"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "执行 validate 并完成收尾包，确保技术栈知识库纳入基线治理。"
  constraints:
    - "validate command: ./prompt-dsl-system/tools/run.sh validate --repo-root ."
    - "must update FACT_BASELINE and COMPLIANCE_MATRIX when coverage changes"
  acceptance:
    - "A4_change_ledger.md"
    - "A5_rollback_plan.md"
    - "A6_cleanup_report.md"
    - "A7_validate_result.json"
  forbidden:
    - "禁止跳过 validate"
    - "禁止修改目标业务仓库"
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
  input_artifact_refs: ["A3_stack_profile_diff.md"]
```
