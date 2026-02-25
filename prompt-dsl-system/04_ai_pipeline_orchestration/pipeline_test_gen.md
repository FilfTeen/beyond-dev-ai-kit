# Pipeline: Test Generation (Company Generic)

## 适用场景

- 为现有 Java8/Spring Boot 模块自动生成单元测试、边界测试和集成测试。

## 输入（必须）

- `allowed_module_root`：模块根目录（必填）。
- `objective`：测试目标与范围描述。
- `context_id` / `trace_id` / `input_artifact_refs`。

## 缺失边界时的硬规则

- 若未提供 `allowed_module_root`：仅扫描分析，不生成测试代码。

## Step 1 - 扫描代码结构 + 识别可测试单元

```yaml
skill: skill_test_gen
parameters:
  module_path: "{{allowed_module_root}}"
  test_scope: "unit"
  objective: "{{objective}}；扫描模块代码结构，识别所有可测试的 Service/Controller/Mapper 类，输出测试策略。"
  constraints:
    - "scan-only"
    - "identify testable units"
  acceptance:
    - "A* testable class inventory"
    - "A* test strategy document"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测命名/字段/逻辑"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    forbidden_paths: ["/sys", "/error", "/util", "/vote"]
    max_change_scope: "read_only"
  fact_policy: {require_scan_before_change: true, unknown_requires_user: true}
  self_monitor_policy: {loop_detection: true, auto_rollback_on_loop: true}
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: []
```

## Step 2 - 生成单元测试代码

```yaml
skill: skill_test_gen
parameters:
  module_path: "{{allowed_module_root}}"
  test_scope: "{{test_scope}}"
  target_classes: "{{target_classes}}"
  coverage_target: "{{coverage_target}}"
  objective: "{{objective}}；按 Step1 策略生成 JUnit4/Mockito 测试代码。"
  constraints:
    - "JUnit4 + Mockito framework"
    - "mirror src/main/java package structure"
  acceptance:
    - "A* generated test files"
    - "A* coverage estimate"
  forbidden:
    - "禁止引入外部 DB 依赖"
    - "禁止硬编码环境变量"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    forbidden_paths: ["/sys", "/error", "/util", "/vote"]
    max_change_scope: "minimal"
  fact_policy: {require_scan_before_change: true, unknown_requires_user: true}
  self_monitor_policy: {loop_detection: true, auto_rollback_on_loop: true}
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: ["A1", "A2"]
```

## Step 3 - 验证 + 覆盖率报告

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "code"
  module_path: "{{allowed_module_root}}"
  objective: "{{objective}}；验证生成的测试代码可编译、可运行，输出覆盖率报告。"
  constraints:
    - "mvn test verification"
    - "coverage report generation"
  acceptance:
    - "A* test verification report"
    - "A* coverage summary"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    forbidden_paths: ["/sys", "/error", "/util", "/vote"]
    max_change_scope: "minimal"
  fact_policy: {require_scan_before_change: true, unknown_requires_user: true}
  self_monitor_policy: {loop_detection: true, auto_rollback_on_loop: true}
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: ["A3"]
```
