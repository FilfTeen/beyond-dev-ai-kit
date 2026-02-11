# Pipeline: Module Migration（模块级迁移装配线 Pipeline）

> [!NOTE]
> **Bypass 使用声明**：本 pipeline 运行时允许使用 `HONGZHI_ALLOW_RUN_WITHOUT_MODULE_PATH=1`。
> 原因：本 pipeline 的所有步骤仅操作 `prompt-dsl-system/**` 内部文件（modes: governance/meta/docs），
> 属于治理类 pipeline，符合 `HONGZHI_COMPANY_CONSTITUTION.md` Rule 16 的许可条件。

## 适用场景

- 针对单个业务模块（如 notice、ownercommittee），生成一组覆盖 SQL portability / API contract / UI wiring / workflow integration 的 staging skills + pipelines。
- 区别于 `pipeline_project_bootstrap` 的项目级粒度，本 pipeline 聚焦单模块迁移需求。
- 所有生成的 skill 默认 status=staging，需通过 `pipeline_skill_promote` 晋级。

## 输入（必须）

- `allowed_module_root`：必须为 `prompt-dsl-system`。
- `project_key`：项目标识（如 xywygl）。
- `module_key`：模块标识（如 notice）。
- `migration_objectives`：迁移目标列表（如 sql_portability, api_parity, ui_parity）。
- `db_dialects`：目标数据库方言列表（如 oracle, mysql, dm8）。
- `context_id` / `trace_id` / `input_artifact_refs`。

## 输入优先级（三层合并 — MODULE_PROFILE_SPEC.md）

1. **Layer0** — 读取 `projects/<project_key>/profile.yaml`（项目全局默认，若存在）。
2. **Layer1** — 读取 `module_profiles/<project_key>/<module_key>.yaml`（declared profile，必须存在，否则输出 checklist）。
3. **Layer2R** — 读取 `module_profiles/<project_key>/<module_key>.roots.discovered.yaml`（roots discovered，若不存在，先运行 Step0 `module_roots_discover.py`）。
4. **Layer2** — 读取 `module_profiles/<project_key>/<module_key>.discovered.yaml`（discovered profile，若不存在，先运行 Step0 `module_profile_scanner.py`）。
5. **合并规则** — `Effective Profile = merge(Layer0, Layer1, Layer2R, Layer2)`。discovered 仅能覆盖 `discovery.*` 字段，不可改变 scope/objectives/identity。`allowed_module_roots` 由 Layer2R 提供。

## 缺失边界时的硬规则

- 若未提供 `allowed_module_root`：仅扫描现有 skill registry，不得创建/修改任何文件。

## Step 0 — 自动发现（Pre-Discovery）

**Freedom: none** — 确定性工具调用

> [!NOTE]
> Step0 在 Step1 前自动运行 `module_roots_discover.py` 和 `module_profile_scanner.py`，
> 生成 `roots.discovered.yaml` 和 `discovered.yaml`。如已存在且未过期，可跳过。

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "运行自动发现工具：(1) module_roots_discover.py --project-key={{project_key}} --module-key={{module_key}} 生成 roots.discovered.yaml；(2) module_profile_scanner.py --project-key={{project_key}} --module-key={{module_key}} 读取 roots 生成 discovered.yaml。"
  constraints:
    - "tool-call only, no creative output"
    - "if Layer1 declared profile missing: STOP, output required_additional_information"
    - "if identity hints (backend_package_hint / web_path_hint) both missing: WARN"
  acceptance:
    - "A0_roots.discovered.yaml exists"
    - "A0_discovered.yaml exists"
  forbidden:
    - "禁止手动编写 discovered 文件内容"
  boundary_policy:
    allowed_module_root: "{{allowed_module_root}}"
    forbidden_paths: ["/sys", "/error", "/util", "/vote"]
  trace_id: "{{trace_id}}"
```

## Step 1 — 模块画像解析 + 迁移计划

**Freedom: high** — 解析深度和迁移拆分粒度由 agent 自主决定

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "governance"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "按三层合并读取 Effective Profile：(1) Layer0 projects/{{project_key}}/profile.yaml；(2) Layer1 module_profiles/{{project_key}}/{{module_key}}.yaml（必须存在，否则输出 required_additional_information checklist）；(3) Layer2 module_profiles/{{project_key}}/{{module_key}}.discovered.yaml（若存在则加载索引，否则建议运行 module_profile_scanner.py）。合并后解析集成点和迁移目标；扫描 skills.json 评估可复用 skill；输出迁移计划树和影响分析。"
  constraints:
    - "scan-only"
    - "Layer1 (declared) MUST exist, otherwise output required_additional_information"
    - "Layer2 (discovered) optional: if missing, recommend running module_profile_scanner.py"
    - "merge precedence: Layer0 < Layer1 < Layer2 (discovery.* only)"
    - "discovered cannot override scope/objectives/identity"
    - "check skill name uniqueness against registry"
    - "decision order: reuse > extend > create"
    - "migration plan must map: objective → integration_point → skill"
  acceptance:
    - "A1_migration_plan.md (tree: objective → integration_point → skill name → action)"
    - "A1_impact_tree.md"
    - "if profile missing: A1_required_additional_information.md"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测模块结构/字段/逻辑"
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

## Step 2 — 模块技能集合列表生成（status=staging）

**Freedom: medium** — 技能拆分粒度由 agent 决定，但必须遵守 SKILL_SPEC schema

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "基于 Step1 迁移计划，为模块 {{module_key}} 生成技能集合列表。每个迁移目标至少一个 skill。命名规范：skill_<module_key>_<verb>_<object>。所有 skill 默认 status=staging。"
  constraints:
    - "at least one skill per migration_objective"
    - "for sql_portability: must generate skill covering Oracle→MySQL+DM8 dual-stack"
    - "skill name: skill_<module_key>_<verb>_<object>"
    - "YAML must validate against SKILL_SPEC.md required schema"
    - "all new skills MUST have status: staging"
    - "output_contract must include summary/artifacts[]/risks[]/next_actions[]"
    - "if discovered profile exists: reference discovery.file_index in skill scope"
    - "if discovered profile missing: output read_refs + suggest running scanner"
  acceptance:
    - "A2_skill_set_list.md (skill name → objective → integration_points)"
    - "A2_skill_yamls/ (directory with all generated YAMLs)"
    - "A2 all skills have status: staging"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止臆测命名/字段/逻辑"
    - "禁止将新 skill 设为 status: deployed"
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

## Step 3 — Template 复制 + Registry 更新（status=staging）

**Freedom: low** — 模板复制和注册是确定性操作

> [!NOTE]
> 可选开关 `materialize_skills`（默认 `false`）。当 `true` 时实际复制 template 并更新 skills.json；
> 当 `false` 时仅输出 skill skeleton 清单（dry-run）。落地的 skill 仍为 `status=staging`，不自动 promote。

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "为 Step2 产出的每个 skill：(1) 复制 templates/skill_template/ → skills/<domain>/skill_<name>/；(2) 填充 YAML（无 placeholder 残留）；(3) 注册到 skills.json（status=staging）。"
  constraints:
    - "registry entry: name/description/version/domain/tags/path/status"
    - "all new entries MUST have status: staging"
    - "path must be repository-relative"
    - "no duplicate names in registry"
    - "no residual {{PLACEHOLDER}} in generated YAMLs"
    - "if materialize_skills=false: output dry-run skeleton list only, do NOT create files"
    - "if materialize_skills=true: copy templates, fill YAMLs, update skills.json"
  acceptance:
    - "A3_updated_skills_json (valid JSON, all new entries status=staging)"
    - "A3_registry_diff.md (before/after)"
    - "Step3 checks: ✓ directories exist, ✓ no placeholders, ✓ references/scripts/assets subdirs"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
    - "禁止删除现有 registry 条目"
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

**Freedom: medium** — pipeline 结构遵循规范，step 内容由 agent 基于 skill 参数生成

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "meta"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "为 Step2/3 产出的每个 skill 生成一个 pipeline_*.md 示例文件。命名：pipeline_<module_key>_<verb>_<object>.md。每个 pipeline 至少 3 步：scan → execute → closure。"
  constraints:
    - "pipeline must reference the corresponding skill by name"
    - "each step must include: context_id/trace_id/mode/objective/constraints/acceptance/forbidden/boundary_policy"
    - "at least 3 steps per pipeline"
    - "naming: pipeline_<module_key>_<verb>_<object>.md"
  acceptance:
    - "A4_pipelines/ (all generated pipeline files)"
    - "A4_pipeline_checklist.md"
    - "if discovered profile exists: pipelines must reference discovery.navindex for read_refs"
    - "if discovered profile missing: pipeline steps must include scanner run suggestion"
  forbidden:
    - "禁止改 /sys,/error,/util,/vote"
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

**Freedom: low** — validate/audit/lint 命令固定

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "docs"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "运行 validate(strict) + audit(scope=all) + lint 校验所有新增 skill/registry/pipeline 的完整性；产出收尾包。"
  constraints:
    - "closure mandatory"
    - "validate: HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root ."
    - "audit: /usr/bin/python3 prompt-dsl-system/tools/skill_template_audit.py --repo-root . --scope all --fail-on-empty"
    - "lint: /usr/bin/python3 prompt-dsl-system/tools/pipeline_contract_lint.py --repo-root . --fail-on-empty"
  acceptance:
    - "A5_validate_result.json (Errors=0)"
    - "A5_audit_result (PASS)"
    - "A5_lint_result (PASS)"
    - "if materialize_skills=true: audit(scope=staging) must PASS"
    - "mandatory closure artifacts: impact_tree, change_ledger, rollback_plan, cleanup_report"
    - "FACT_BASELINE.md updated (skill/pipeline counts)"
    - "COMPLIANCE_MATRIX.md updated (if new coverage)"
    - "skills.json status (mandatory declaration):"
    - "  skills.json updated = true, new entry count = N, all status = staging"
  forbidden:
    - "禁止跳过 validate/audit/lint"
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

## Step 6 — Promote 建议（可选，需用户显式要求）

**Freedom: low** — 仅建议，不自动执行

```yaml
skill: skill_hongzhi_universal_ops
parameters:
  mode: "docs"
  module_path: "{{allowed_module_root}}"
  allowed_module_root: "{{allowed_module_root}}"
  objective: "列出所有 staging skill 的 promote 建议：哪些已通过 audit+lint 可晋级，哪些需补充。不自动 promote，仅输出建议列表。用户可使用 pipeline_skill_promote.md 逐个晋级。"
  constraints:
    - "scan-only, no modifications"
    - "list each staging skill with audit/lint status"
    - "do NOT auto-promote"
  acceptance:
    - "A6_promote_suggestions.md (skill → audit_pass → lint_pass → recommend: yes/no)"
  forbidden:
    - "禁止自动修改 skills.json status"
    - "禁止跳过 audit/lint 检查"
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
  input_artifact_refs: ["A5"]
```
