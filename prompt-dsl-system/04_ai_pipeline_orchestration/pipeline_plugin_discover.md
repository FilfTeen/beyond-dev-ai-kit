# Pipeline: Plugin Discover (Status -> Decide -> Discover + Hint Loop Plan)

## 适用场景

- 在不修改目标业务工程的前提下，通过 `hongzhi_ai_kit` 进行治理判定与只读发现扫描。
- 输出机器可解析状态行与能力文件路径，供 agent 后续规划使用。
- 当发现结果低置信度时，输出 `--apply-hints` 的下一步命令；默认不自动二次执行。

## 输入（必须）

- `allowed_module_root`：必须为 `prompt-dsl-system`。
- `repo_root`：目标业务工程路径（只读扫描）。
- `enable_hint_loop`：是否允许自动执行一次 `--apply-hints` rerun（默认 false）。
- `context_id` / `trace_id` / `input_artifact_refs`。

## Step 1 — Status (Governance Preflight)

```yaml
skill: skill_governance_plugin_status
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  repo_root: "{{repo_root}}"
  objective: "先执行 status，输出 HONGZHI_STATUS / HONGZHI_GOV_BLOCK 机器行。"
  constraints:
    - "scan-only"
    - "read-only"
    - "must respect governance gate"
  acceptance:
    - "A1_plugin_status.md"
    - "A1 must include HONGZHI_STATUS"
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

## Step 2 — Decide (Hard Gate)

Decision rule (hard-coded, no ambiguity):

1. If stdout contains `HONGZHI_GOV_BLOCK` or status exit code is `10/11/12`, stop pipeline immediately.
2. Emit machine-readable decision artifact and keep `repo_root` zero-write.
3. Only when governance is allowed (`exit=0`) continue to Step 3.

```yaml
skill: skill_governance_plugin_runner
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  command: "status"
  repo_root: "{{repo_root}}"
  objective: "根据 Step1 结果做硬判定：blocked 则退出，allowed 才进入 discover。"
  constraints:
    - "docs-only decision"
    - "if blocked must surface HONGZHI_GOV_BLOCK verbatim"
    - "no writes to target repo"
  acceptance:
    - "A2_governance_decision.md"
    - "A2 must include decision=blocked|allowed"
    - "blocked path must include machine-readable reason"
  forbidden:
    - "禁止绕过治理判定直接执行 discover"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    forbidden_paths: ["/sys", "/error", "/util", "/vote"]
    max_change_scope: "none"
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: ["A1_plugin_status.md"]
```

## Step 3 — Discover (Only if Allowed)

```yaml
skill: skill_governance_plugin_discover_with_hints
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  repo_root: "{{repo_root}}"
  enable_hint_loop: "{{enable_hint_loop | default(false)}}"
  objective: "治理允许后执行 discover，只写 workspace/state，并输出 HONGZHI_CAPS；若低置信度则输出 HONGZHI_HINTS 与 rerun 命令。"
  constraints:
    - "must keep target repo read-only"
    - "workspace/global state must be outside target repo"
    - "supports --smart and --max-files/--max-seconds limits"
    - "must not auto rerun with hints unless enable_hint_loop=true"
  acceptance:
    - "A3_capabilities_pointer.txt"
    - "A3_capabilities_snapshot.json"
    - "A3 must include HONGZHI_CAPS line and capabilities schema keys"
    - "if needs_human_hint=1: include HONGZHI_HINTS and rerun command template"
  forbidden:
    - "治理 blocked 时禁止执行 discover"
    - "禁止写入目标工程"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    forbidden_paths: ["/sys", "/error", "/util", "/vote"]
    max_change_scope: "none"
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: ["A2_governance_decision.md"]
```

## Step 4 — Hint Loop Decision (No Auto-Rerun by Default)

Decision rule:

1. If Step 3 summary has `needs_human_hint=1`, pipeline **must** emit a NavIndex entry with:
   - `hints_path` from `HONGZHI_HINTS`
   - runnable command: `hongzhi-ai-kit discover --repo-root <repo> --apply-hints <hints_path> [--hint-strategy aggressive]`
2. If `enable_hint_loop=false`, stop after emitting recommendation (default behavior).
3. Only if `enable_hint_loop=true`, run exactly one rerun and emit both run pointers.
