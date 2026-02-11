# Pipeline: Plugin Discover（Governed, Read-Only）

## 适用场景

- 在不修改目标业务工程的前提下，通过 `hongzhi_ai_kit` 获取模块能力摘要。
- 产出可被 agent 解析的能力文件路径与 NavIndex（仅建议，不直接改目标工程）。

## 输入（必须）

- `allowed_module_root`：必须为 `prompt-dsl-system`。
- `repo_root`：目标业务工程路径（只读扫描）。
- `context_id` / `trace_id` / `input_artifact_refs`。

## Step 0 — Plugin Status Preflight

```yaml
skill: skill_governance_plugin_runner
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  command: "status"
  repo_root: "{{repo_root}}"
  objective: "在执行 discover 前验证治理状态、allow/deny/token 条件。"
  constraints:
    - "scan-only"
    - "respect governance gate"
  acceptance:
    - "A0_plugin_status.md"
  forbidden:
    - "禁止修改目标工程"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    forbidden_paths: ["/sys", "/error", "/util", "/vote"]
    max_change_scope: "none"
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: []
```

## Step 1 — Plugin Discover (Workspace Only)

```yaml
skill: skill_governance_plugin_runner
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  command: "discover"
  repo_root: "{{repo_root}}"
  objective: "在治理允许时执行 discover，并从 stdout 获取 HONGZHI_CAPS 能力文件路径。"
  constraints:
    - "must keep target repo read-only"
    - "workspace/global state must be outside target repo"
  acceptance:
    - "A1_capability_pointer.txt"
    - "A1_capabilities_snapshot.json"
    - "A1 includes HONGZHI_CAPS line"
  forbidden:
    - "禁止写入目标工程"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    forbidden_paths: ["/sys", "/error", "/util", "/vote"]
    max_change_scope: "none"
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: ["A0"]
```

## Step 2 — Read Capabilities and Produce Actionable Suggestions

```yaml
skill: skill_governance_plugin_runner
parameters:
  mode: "docs"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  command: "status"
  repo_root: "{{repo_root}}"
  objective: "读取 Step1 的 capabilities.json，并根据 roots/artifacts/metrics 输出下一步建议。"
  constraints:
    - "docs-only"
    - "no direct source modifications"
    - "if read_refs non-empty must mention NavIndex"
    - "read_refs: [A1_capabilities_snapshot.json]"
  acceptance:
    - "A2_discovery_recommendations.md"
    - "A2 includes NavIndex and prioritized next actions"
  forbidden:
    - "禁止直接执行迁移写入"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    forbidden_paths: ["/sys", "/error", "/util", "/vote"]
    max_change_scope: "none"
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: ["A1"]
```
