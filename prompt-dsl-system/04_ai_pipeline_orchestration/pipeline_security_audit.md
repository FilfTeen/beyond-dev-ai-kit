# Pipeline: Security Audit (Company Generic)

## 适用场景

- 对 Java8/Spring Boot 模块执行安全审计，覆盖 SQL 注入、XSS、认证授权、敏感数据暴露。

## 输入（必须）

- `allowed_module_root`：审计目标模块（必填）。
- `objective`：审计目标与重点领域。
- `context_id` / `trace_id` / `input_artifact_refs`。

## 缺失边界时的硬规则

- 安全审计始终为只读操作，不改动任何代码。

## Step 1 - SQL 注入 + 数据暴露扫描

```yaml
skill: skill_security_audit
parameters:
  module_path: "{{allowed_module_root}}"
  audit_depth: "{{audit_depth}}"
  focus_areas: ["sql_injection", "data_exposure"]
  objective: "{{objective}}；扫描 MyBatis XML 和 Controller 层，识别 SQL 注入和敏感数据暴露风险。"
  constraints:
    - "read-only"
    - "scan all mapper XML files"
  acceptance:
    - "A* SQL injection report"
    - "A* data exposure findings"
  forbidden:
    - "禁止修改任何代码"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    max_change_scope: "read_only"
  fact_policy: {require_scan_before_change: true, unknown_requires_user: true}
  self_monitor_policy: {loop_detection: true, auto_rollback_on_loop: true}
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: []
```

## Step 2 - 认证授权 + XSS 审查

```yaml
skill: skill_security_audit
parameters:
  module_path: "{{allowed_module_root}}"
  audit_depth: "{{audit_depth}}"
  focus_areas: ["auth", "xss", "csrf"]
  objective: "{{objective}}；检查权限注解覆盖、XSS 防护、CSRF 配置。"
  constraints:
    - "read-only"
    - "check all @Controller and @RestController classes"
  acceptance:
    - "A* auth coverage matrix"
    - "A* XSS findings"
  forbidden:
    - "禁止修改任何代码"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    max_change_scope: "read_only"
  fact_policy: {require_scan_before_change: true, unknown_requires_user: true}
  self_monitor_policy: {loop_detection: true, auto_rollback_on_loop: true}
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: ["A1", "A2"]
```

## Step 3 - 综合安全报告 + 修复计划

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；汇总安全发现，按严重度排序，生成修复优先级与行动计划。"
  constraints:
    - "read-only"
    - "severity-ordered report"
  acceptance:
    - "A* security audit report (full)"
    - "A* fix priority plan"
  forbidden:
    - "禁止修改任何代码"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    max_change_scope: "read_only"
  fact_policy: {require_scan_before_change: true, unknown_requires_user: true}
  self_monitor_policy: {loop_detection: true, auto_rollback_on_loop: true}
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: ["A1", "A2", "A3", "A4"]
```
