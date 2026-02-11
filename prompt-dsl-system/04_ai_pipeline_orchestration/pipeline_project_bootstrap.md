# Pipeline: Project Bootstrap（项目级装配线 Pipeline）

> [!NOTE]
> **Bypass 使用声明**：本 pipeline 运行时允许使用 `HONGZHI_ALLOW_RUN_WITHOUT_MODULE_PATH=1`。
> 原因：本 pipeline 的所有步骤仅操作 `prompt-dsl-system/**` 内部文件（modes: governance/meta/docs），
> 属于治理类 pipeline，符合 `HONGZHI_COMPANY_CONSTITUTION.md` Rule 16 的许可条件。
> **禁止**将此 bypass 用于任何修改业务代码（code/sql/frontend/process/release 模式）的 pipeline。

## 适用场景

- 从一个项目或模块需求出发，批量生成该项目所需的全部 skill + pipeline，实现"项目级装配线"。
- 区别于 `pipeline_skill_creator`（单 skill 粒度），本 pipeline 一次装配多个 skill。
- 所有生成的 skill 默认 status=staging，需通过 audit + 人工确认后升级为 deployed。
- **单模块迁移**：若用户目标是单个模块迁移（如 notice Oracle→MySQL+DM8），应使用 `pipeline_module_migration.md`。

## 输入（必须）

- `allowed_module_root`：必须为 `prompt-dsl-system`。
- `project_scope`：项目/模块名称及功能边界描述。
- `target_capabilities`：目标能力列表（每项对应一个潜在 skill）。
- `project_key`（可选）：若提供，Step1 将尝试读取 `projects/<project_key>/profile.yaml`（见 `PROJECT_PROFILE_SPEC.md`）。
- `context_id` / `trace_id` / `input_artifact_refs`。

## 缺失边界时的硬规则

- 若未提供 `allowed_module_root`：仅扫描现有 skill registry，不得创建/修改任何文件。

## Step 1 — 项目边界解析 + 能力映射

**Freedom: high** — 解析深度和能力拆分粒度由 agent 自主决定

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "若提供 project_key，先读取 projects/{{project_key}}/profile.yaml（按 PROJECT_PROFILE_SPEC.md 格式）作为输入；若 profile 不存在，必须输出 required_additional_information checklist（禁止猜测项目结构）。解析项目 {{project_scope}} 的模块边界和目标能力 {{target_capabilities}}；扫描现有 skills.json 和 SKILL_SPEC.md，评估哪些能力需要新 skill、哪些可复用现有 skill；输出能力→skill 映射表和影响树。"
  constraints:
    - "scan-only"
    - "if project_key provided: read projects/<project_key>/profile.yaml"
    - "if profile missing: output required_additional_information checklist (never guess project structure)"
    - "check skill name uniqueness against registry"
    - "check domain folder existence"
    - "decision order: reuse > extend > create"
  acceptance:
    - "A1_impact_tree.md"
    - "A1_capability_skill_map.md (capability → skill name → action: reuse/extend/create)"
    - "A1 includes: registry current state, naming collision check, domain mapping"
    - "if profile missing: A1_required_additional_information.md"
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
  decision_policy: {dependency_strategy_order: ["reuse", "extend", "create"], choose_best_route_with_tradeoff: true}
  sql_policy: {prefer_portable_sql: true, dual_sql_when_needed: ["oracle", "mysql"]}
  context_id: "{{context_id}}"
  trace_id: "{{trace_id}}"
  input_artifact_refs: []
```

## Step 2 — 批量 Skill YAML 生成（status=staging）

**Freedom: medium** — YAML 内容由 agent 生成，但必须严格遵守 SKILL_SPEC schema + staging 规则

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "基于 Step1 能力映射表，为每个 action=create 的 skill 生成 YAML 文件；所有新 skill 默认 status=staging；必须包含 SKILL_SPEC 全部必填字段。"
  constraints:
    - "skill name must follow: skill_<domain>_<verb>_<object>"
    - "YAML must validate against SKILL_SPEC.md required schema"
    - "all new skills MUST have status: staging"
    - "output_contract must include summary/artifacts[]/risks[]/next_actions[]"
    - "parameters must include context_id/trace_id/input_artifact_refs/mode/objective/constraints/acceptance/forbidden/boundary_policy/fact_policy/self_monitor_policy/decision_policy/sql_policy"
    - "examples must include at least one complete input/output pair per skill"
  acceptance:
    - "A2_skill_yamls/ (directory containing all generated skill YAMLs)"
    - "A2_skill_validation_checklist.md"
    - "A2 all skills have status: staging"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测命名/字段/逻辑"
    - "禁止修改现有 skill_hongzhi_universal_ops.yaml 的核心逻辑"
    - "禁止将新 skill 设为 status: deployed（必须为 staging）"
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

## Step 3 — Template 初始化 + Registry 更新

**Freedom: low** — template 复制是确定性操作，registry 更新按公式执行

复用 `pipeline_skill_creator` Step 3 机制，对每个 Step2 产出的 skill 执行：

### Sub-step 3a: Template Skeleton Generation (low freedom)

为每个新 skill（若目标目录不存在）：

1. 复制 `templates/skill_template/` → `skills/<domain>/skill_<domain>_<verb>_<object>/`
2. 重命名 `skill.yaml.template` → `skill_<domain>_<verb>_<object>.yaml`
3. 重命名 `README.template` → `README.md`（references/scripts/assets 三个子目录）
4. 用 Step2 产出填充 `{{PLACEHOLDER}}` 值
5. 验证填充后 YAML 符合 SKILL_SPEC.md Required YAML Schema

若目标目录已存在 → 跳过 template 复制，直接更新 YAML。

### Sub-step 3b: Registry + Baseline Update

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "将 Step2 批量产出的新 skill YAML 逐个注册到 skills.json（status=staging），并更新 FACT_BASELINE.md 中的 skill 计数和分布信息。"
  constraints:
    - "registry entry must include: name/description/version/domain/tags/path/status"
    - "all new entries MUST have status: staging"
    - "path must be repository-relative"
    - "FACT_BASELINE must reflect new skill counts (staging vs deployed)"
    - "no duplicate names in registry"
  acceptance:
    - "A3_updated_skills_json (valid JSON array, all entries have required fields + status)"
    - "A3_updated_fact_baseline.md"
    - "A3_registry_diff.md (before/after comparison)"
    - "Step3 verifiable checks (all must PASS):"
    - "  ✓ each target skill directory exists"
    - "  ✓ all skill YAMLs have no residual {{PLACEHOLDER}} patterns"
    - "  ✓ references/ scripts/ assets/ subdirectories exist (from template)"
    - "  ✓ all new skills.json entries have status: staging"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测命名/字段/逻辑"
    - "禁止删除现有 registry 条目"
    - "禁止修改 deprecated skills"
    - "禁止将新 skill status 设为 deployed"
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

## Step 4 — 批量 Pipeline 示例生成

**Freedom: medium** — pipeline 结构遵循现有格式，step 内容由 agent 基于新 skill 参数生成

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "基于 Step2/Step3 产出的所有新 skill，为每个 skill 生成一个可用的 pipeline_*.md 示例文件；pipeline 命名规范：pipeline_<domain>_<verb>_<object>.md。"
  constraints:
    - "pipeline must reference the corresponding skill by name"
    - "each step must include: context_id/trace_id/input_artifact_refs/mode/objective/constraints/acceptance/forbidden/boundary_policy"
    - "pipeline must follow existing pipeline_*.md format (markdown + yaml blocks)"
    - "at least 3 steps: scan → execute → closure"
    - "naming: pipeline_<domain>_<verb>_<object>.md"
  acceptance:
    - "A4_pipelines/ (directory containing all generated pipeline example files)"
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

**Freedom: low** — validate/audit/lint 命令固定，产物清单确定性

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "docs"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "运行 validate + audit + lint 校验所有新增 skill/registry/pipeline 的完整性；产出完整收尾包。"
  constraints:
    - "closure mandatory"
    - "validate command: ./prompt-dsl-system/tools/run.sh validate --repo-root ."
    - "ops_guard command: /usr/bin/python3 prompt-dsl-system/tools/ops_guard.py --repo-root . --allowed-root prompt-dsl-system"
    - "audit command: /usr/bin/python3 prompt-dsl-system/tools/skill_template_audit.py --repo-root . --scope all"
    - "lint command: /usr/bin/python3 prompt-dsl-system/tools/pipeline_contract_lint.py --repo-root ."
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
    - "  if new skill added: skills.json updated = true, new entry count = N, all status = staging"
    - "  if no new skill: skills.json updated = false, reason = <reason>"
    - "A5_validate_result.json (Errors=0)"
    - "skill_template_audit PASS (run: python3 tools/skill_template_audit.py --repo-root . --scope all)"
    - "pipeline_contract_lint PASS (run: python3 tools/pipeline_contract_lint.py --repo-root .)"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测命名/字段/逻辑"
    - "禁止跳过 validate/audit/lint 步骤"
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
