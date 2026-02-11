# Pipeline: Skill Promote（Skill 晋级 Pipeline）

> [!NOTE]
> **Bypass 使用声明**：本 pipeline 运行时允许使用 `HONGZHI_ALLOW_RUN_WITHOUT_MODULE_PATH=1`。
> 原因：本 pipeline 仅操作 `prompt-dsl-system/**` 内部文件（modes: governance/docs），
> 属于治理类 pipeline，符合 `HONGZHI_COMPANY_CONSTITUTION.md` Rule 16 的许可条件。

## 适用场景

- 将通过审计的 staging skill 晋级为 deployed。
- 前置条件：validate PASS + audit PASS + lint PASS + 人工确认。
- Freedom: **low** — 所有操作确定性执行。

## 输入（必须）

- `allowed_module_root`：必须为 `prompt-dsl-system`。
- `skill_name`：要晋级的 skill 名称（必须在 skills.json 中 status=staging）。
- `reviewer`：审批人标识。
- `promotion_reason`：晋级原因。
- `context_id` / `trace_id`。

## 缺失边界时的硬规则

- 若 `skill_name` 在 registry 中不存在或 status ≠ staging：中断并报错。

## Step 1 — 前置校验（不改文件）

**Freedom: low** — 校验命令固定

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "校验 {{skill_name}} 是否满足晋级条件：(1) skills.json 中存在且 status=staging；(2) validate PASS；(3) audit --scope staging PASS；(4) lint PASS。"
  constraints:
    - "scan-only, no file modifications"
    - "validate command: ./prompt-dsl-system/tools/run.sh validate --repo-root ."
    - "audit command: /usr/bin/python3 prompt-dsl-system/tools/skill_template_audit.py --repo-root . --scope staging"
    - "lint command: /usr/bin/python3 prompt-dsl-system/tools/pipeline_contract_lint.py --repo-root ."
    - "all three must PASS before proceeding"
  acceptance:
    - "A1_precondition_report.md (PASS/FAIL for each check)"
    - "if any FAIL: pipeline must STOP"
  forbidden:
    - "禁止在此步骤修改任何文件"
    - "禁止跳过任何校验"
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

## Step 2 — 执行晋级

**Freedom: low** — JSON 字段更新是确定性操作

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "更新 skills.json 中 {{skill_name}} 的 status 从 staging 改为 deployed；更新 FACT_BASELINE.md 中的 staging/deployed 计数。"
  constraints:
    - "only modify status field of the target skill"
    - "must not change any other registry entries"
    - "must not change skill YAML file content"
    - "FACT_BASELINE staging/deployed counts must be updated"
  acceptance:
    - "A2_promotion_ledger.md (mandatory, fixed schema below):"
    - "  skill_name: {{skill_name}}"
    - "  registry_path: <skills.json entry path>"
    - "  status_before: staging"
    - "  status_after: deployed"
    - "  reviewer: {{reviewer}}"
    - "  reason: {{promotion_reason}}"
    - "  audit_pass: true/false"
    - "  lint_pass: true/false"
    - "  timestamp: <ISO-8601>"
    - "A2_updated_skills_json (diff showing status change)"
  forbidden:
    - "禁止修改非目标 skill 的 registry 条目"
    - "禁止修改 skill YAML 文件内容"
    - "禁止将 deployed/deprecated skill 的 status 改为其他值"
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
  input_artifact_refs: ["A1"]
```

## Step 3 — 晋级后校验 + 收尾

**Freedom: low** — validate/audit 命令固定

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "docs"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "晋级后运行 validate + audit，确认 skills.json 一致性；产出收尾包。"
  constraints:
    - "closure mandatory"
    - "validate command: ./prompt-dsl-system/tools/run.sh validate --repo-root ."
    - "audit command: /usr/bin/python3 prompt-dsl-system/tools/skill_template_audit.py --repo-root . --scope all"
  acceptance:
    - "A3_validate_result.json (Errors=0)"
    - "A3_audit_result (PASS)"
    - "A3_promotion_ledger_final.md (must reference A2_promotion_ledger.md, append validate/audit result)"
    - "mandatory closure artifacts: impact_tree, change_ledger, rollback_plan, cleanup_report"
    - "skills.json status (mandatory declaration):"
    - "  skills.json updated = true, {{skill_name}} status = deployed"
  forbidden:
    - "禁止跳过 validate/audit"
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
