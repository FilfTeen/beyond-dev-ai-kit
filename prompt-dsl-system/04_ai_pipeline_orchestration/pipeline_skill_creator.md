# Pipeline: Skill Creator（公司域 Skill 创建 Pipeline）

> [!NOTE]
> **Bypass 使用声明**：本 pipeline 运行时允许使用 `HONGZHI_ALLOW_RUN_WITHOUT_MODULE_PATH=1`。
> 原因：本 pipeline 的所有步骤仅操作 `prompt-dsl-system/**` 内部文件（modes: governance/meta/docs），
> 属于治理类 pipeline，符合 `HONGZHI_COMPANY_CONSTITUTION.md` Rule 16 的许可条件。
> **禁止**将此 bypass 用于任何修改业务代码（code/sql/frontend/process/release 模式）的 pipeline。

## 适用场景

- 从需求出发，生成 skill YAML → 更新 registry → 更新 FACT_BASELINE → 生成 pipeline 示例 → 校验收尾。
- 等价于 `skill-creator` 能力，但仅在博彦泓智公司域（`prompt-dsl-system/**`）内生效。

## 输入（必须）

- `allowed_module_root`：必须为 `prompt-dsl-system`（skill创建只允许在 DSL 系统内）。
- `objective`：新 skill 的需求描述（功能、适用场景、输入输出）。
- `context_id` / `trace_id` / `input_artifact_refs`。

## 缺失边界时的硬规则

- 若未提供 `allowed_module_root`：仅扫描现有 skill registry，不得创建/修改任何文件。

## Step 1 — 需求扫描 + 影响树 + 可行性评估（不改文件）

**Freedom: high** — 扫描范围和评估深度由 agent 自主决定

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"  # alias for allowed_module_root
  allowed_module_root: "{{allowed_module_root}}"
  objective: "{{objective}}；扫描现有 skills.json 和 SKILL_SPEC.md，评估新 skill 是否与现有 universal skill 重复，输出影响树和可行性评估。"
  constraints:
    - "scan-only"
    - "check skill name uniqueness against registry"
    - "check domain folder existence"
    - "decision order: compat > self-contained > minimal-invasive"
  acceptance:
    - "A1_impact_tree.md"
    - "A1 includes: registry current state, naming collision check, domain mapping"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测命名/字段/逻辑"
    - "禁止在此步骤创建或修改任何文件"
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

## Step 2 — 生成 Skill YAML

**Freedom: medium** — YAML 内容由 agent 生成，但必须严格遵守 SKILL_SPEC schema

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"  # alias for allowed_module_root
  allowed_module_root: "{{allowed_module_root}}"
  objective: "基于 Step1 评估结果和 SKILL_SPEC.md 规范，生成新 skill 的 YAML 文件；必须包含 name/description/version/domain/tags/parameters/prompt_template/output_contract/examples 全部字段。"
  constraints:
    - "skill name must follow: skill_<domain>_<verb>_<object>"
    - "YAML must validate against SKILL_SPEC.md required schema"
    - "output_contract must include summary/artifacts[]/risks[]/next_actions[]"
    - "parameters must include context_id/trace_id/input_artifact_refs/mode/objective/constraints/acceptance/forbidden/boundary_policy/fact_policy/self_monitor_policy/decision_policy/sql_policy"
    - "examples must include at least one complete input/output pair"
  acceptance:
    - "A2_skill_yaml.yaml (valid YAML, spec-compliant)"
    - "A2_skill_validation_checklist.md"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测命名/字段/逻辑"
    - "禁止修改现有 skill_hongzhi_universal_ops.yaml 的核心逻辑"
    - "禁止引入第二个 active skill（除非本步骤明确产出新 skill）"
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

## Step 3 — Template 初始化 + Registry 更新 + FACT_BASELINE

**Freedom: low** — template 复制是确定性操作，registry 更新按公式执行

### Sub-step 3a: Template Skeleton Generation (low freedom)

若目标 skill 目录不存在：

1. 复制 `templates/skill_template/` → `skills/<domain>/skill_<domain>_<verb>_<object>/`
2. 重命名 `skill.yaml.template` → `skill_<domain>_<verb>_<object>.yaml`
3. 重命名 `README.template` → `README.md`（references/scripts/assets 三个子目录）
4. 用 Step2 产出填充 `{{PLACEHOLDER}}` 值
5. 验证填充后 YAML 符合 SKILL_SPEC.md Required YAML Schema

若目标 skill 目录已存在 → 跳过 template 复制，直接更新 YAML。

### Sub-step 3b: Registry + Baseline Update

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"  # alias for allowed_module_root
  allowed_module_root: "{{allowed_module_root}}"
  objective: "将 Step2 产出的新 skill YAML 注册到 skills.json，并更新 FACT_BASELINE.md 中的 skill 计数和分布信息；确保 registry 条目与 YAML 文件 1:1 对应。"
  constraints:
    - "registry entry must include: name/description/version/domain/tags/path"
    - "path must be repository-relative"
    - "FACT_BASELINE must reflect new active skills count and domain distribution"
    - "no duplicate names in registry"
  acceptance:
    - "A3_updated_skills_json (valid JSON array, all entries have required fields)"
    - "A3_updated_fact_baseline.md"
    - "A3_registry_diff.md (before/after comparison)"
    - "Step3 verifiable checks (all must PASS):"
    - "  ✓ target skill directory exists: skills/<domain>/skill_<domain>_<verb>_<object>/"
    - "  ✓ skill YAML has no residual {{PLACEHOLDER}} patterns"
    - "  ✓ references/ scripts/ assets/ subdirectories exist (from template)"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测命名/字段/逻辑"
    - "禁止删除现有 registry 条目"
    - "禁止修改 deprecated skills"
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

## Step 4 — 生成 Pipeline 示例

**Freedom: medium** — pipeline 结构遵循现有格式，step 内容由 agent 基于新 skill 参数生成

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"  # alias for allowed_module_root
  allowed_module_root: "{{allowed_module_root}}"
  objective: "基于新 skill 的 parameters 和 examples，生成一个可用的 pipeline_*.md 示例文件；pipeline 每步必须包含完整的 skill 调用参数块。"
  constraints:
    - "pipeline must reference the new skill by name"
    - "each step must include: context_id/trace_id/input_artifact_refs/mode/objective/constraints/acceptance/forbidden/boundary_policy"
    - "pipeline must follow existing pipeline_*.md format (markdown + yaml blocks)"
    - "at least 3 steps: scan → execute → closure"
  acceptance:
    - "A4_pipeline_example.md (valid pipeline, yaml blocks parseable)"
    - "A4_pipeline_step_checklist.md"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测命名/字段/逻辑"
    - "禁止修改现有 pipeline 文件"
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
  input_artifact_refs: ["A2", "A3"]
```

## Step 5 — 校验 + 收尾文档

**Freedom: low** — validate/ops_guard 命令固定，产物清单确定性

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "docs"
  module_path: "{{allowed_module_root}}"  # alias for allowed_module_root
  allowed_module_root: "{{allowed_module_root}}"
  objective: "运行 validate 校验新增 skill/registry/pipeline 的完整性；产出完整收尾包。"
  constraints:
    - "closure mandatory"
    - "validate command: ./prompt-dsl-system/tools/run.sh validate --repo-root ."
    - "ops_guard command: /usr/bin/python3 prompt-dsl-system/tools/ops_guard.py --repo-root . --allowed-root prompt-dsl-system"
    - "if bypass was used, change_ledger must record: bypass=HONGZHI_ALLOW_RUN_WITHOUT_MODULE_PATH=1, reason, scope"
  acceptance:
    - "mandatory artifacts:"
    - "  A1_impact_tree.md (from Step1 or accumulated)"
    - "  A2_change_ledger.md (逐文件变更记录)"
    - "  A3_rollback_plan.md (逐文件回退步骤)"
    - "  A4_cleanup_report.md (垃圾文件清单，无则写 none)"
    - "docs updates (if applicable):"
    - "  COMPLIANCE_MATRIX.md (if new rules or coverage changes)"
    - "  FACT_BASELINE.md (if skill/pipeline/tool counts change)"
    - "skills.json status (mandatory declaration):"
    - "  if new skill added: skills.json updated = true, new entry count = N"
    - "  if no new skill: skills.json updated = false, reason = <reason>"
    - "A5_validate_result.json (Errors=0)"
    - "skill_template_audit PASS (run: python3 tools/skill_template_audit.py --repo-root .)"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测命名/字段/逻辑"
    - "禁止跳过 validate 步骤"
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
  input_artifact_refs: ["A3", "A4"]
```
