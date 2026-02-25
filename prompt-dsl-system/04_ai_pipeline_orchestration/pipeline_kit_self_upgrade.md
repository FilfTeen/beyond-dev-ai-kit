# Pipeline: Kit Self Upgrade (Kit-Only 主线升级)

## 适用场景

- 对 `beyond-dev-ai-kit` 本体做升级前，先进行量化自检。
- 将“通用性/完整度/健壮性/效率/可扩展性/安全治理/主线聚焦”转为可执行评分。
- 输出可回滚、可追踪的升级计划。
- 当输入目标明确为 `beyond-dev-ai-kit` 的 `prompt/DSL/skill/pipeline` 套件升级时，作为默认专用主线。

## 输入（必须）

- `allowed_module_root`: 必须为 `prompt-dsl-system`。
- `repo_root`: 套件仓库根路径（通常为 `.`）。
- `context_id` / `trace_id` / `input_artifact_refs`。

## Step 0 — 权威规范对齐（先于自检）

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  repo_root: "{{repo_root}}"
  objective: "先对齐权威规范：以 HONGZHI_TASK_OPERATING_REQUIREMENTS.md 的 17 条为最高约束，检查并输出对 prompt/DSL/skill/pipeline 的落地差距。"
  constraints:
    - "must scan authoritative file before proposing edits"
    - "must include hongzhi-work-dev skill upgrade alignment notes"
    - "kit-only scope"
  acceptance:
    - "A0_authority_alignment.md"
    - "A0_rule_gap_map.md"
  forbidden:
    - "禁止跳过权威规范扫描"
    - "禁止无依据改动"
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

## Step 1 — 质量自检评分（kit-only）

```yaml
skill: skill_governance_audit_kit_quality
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  repo_root: "{{repo_root}}"
  objective: "运行 kit_selfcheck.py 输出质量评分与缺口列表；仅允许 kit 内路径写入报告。"
  constraints:
    - "kit-only"
    - "no external business repo mutation"
    - "must output json + md reports"
  acceptance:
    - "A1_impact_tree.md"
    - "A1_kit_selfcheck_report.json"
    - "A1_kit_selfcheck_report.md"
  forbidden:
    - "禁止修改外部业务仓库"
    - "禁止跳过质量评分"
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
  input_artifact_refs: ["A0_authority_alignment.md", "A0_rule_gap_map.md"]
```

## Step 2 — 缺口优先级与升级路线

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "基于 A1 报告输出优先级路线：P0/P1/P2 改进项、收益/风险/成本对比、建议执行顺序。"
  constraints:
    - "must include tradeoff table"
    - "must keep kit-only scope"
  acceptance:
    - "A2_upgrade_backlog.md"
    - "A2_route_decision.md"
  forbidden:
    - "禁止越界修改业务仓库"
    - "禁止无证据决策"
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
  input_artifact_refs: ["A0_rule_gap_map.md", "A1_kit_selfcheck_report.json"]
```

## Step 3 — 最小侵入升级实施（kit-only）

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "按 A2 优先级实施最小侵入升级，仅修改 prompt/DSL/skill/pipeline/tooling 文档与脚本。"
  constraints:
    - "kit-only writes"
    - "keep backward compatibility where possible"
    - "must update compliance/baseline when coverage changes"
    - "must sync external skill authority layer: /Users/dwight/Downloads/【洪智科技】本地存档/hongzhi-work-dev/SKILL.md when governance text changes"
    - "use closure templates: prompt-dsl-system/tools/artifacts/templates/kit_self_upgrade/"
  acceptance:
    - "A3_change_ledger.md"
    - "A3_rollback_plan.md"
    - "A3_cleanup_report.md"
    - "A3_authority_sync_log.md"
  forbidden:
    - "禁止越界到外部业务仓库"
    - "禁止大范围无目标重构"
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
  input_artifact_refs: ["A0_rule_gap_map.md", "A2_upgrade_backlog.md"]
```

## Step 4 — 校验与收尾

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "docs"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "执行 validate + lint + 收尾文档，确保升级可复现、可回滚、可审计。"
  constraints:
    - "validate: ./prompt-dsl-system/tools/run.sh validate --repo-root ."
    - "strict self-upgrade gate: ./prompt-dsl-system/tools/run.sh self-upgrade --repo-root . --strict-self-upgrade"
    - "lint: /usr/bin/python3 prompt-dsl-system/tools/pipeline_contract_lint.py --repo-root . --fail-on-empty"
    - "agent capability audit: /usr/bin/python3 prompt-dsl-system/tools/agent_capability_audit.py --repo-root . --single-calls 12000 --concurrent-calls 16000 --concurrency 48"
  acceptance:
    - "A4_validate_result.json"
    - "A4_release_notes.md"
    - "A4_agent_capability_audit.json"
    - "A4_agent_capability_audit.md"
  forbidden:
    - "禁止跳过校验"
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
  input_artifact_refs: ["A3_change_ledger.md", "A3_authority_sync_log.md"]
```
