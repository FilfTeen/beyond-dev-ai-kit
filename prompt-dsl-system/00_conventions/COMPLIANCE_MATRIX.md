# Compliance Matrix (Original 15 Requirements + R16~R19 -> Current Implementation)

## Validation Snapshot

- Validate command: `./prompt-dsl-system/tools/run.sh validate --repo-root .`
- Result: `Errors=0, Warnings=0`

| ID | Original Requirement | Enforced By | Gate/Tool | Status |
|---|---|---|---|---|
| R01 | 公司域隔离，仅在公司任务生效 | `HONGZHI_COMPANY_CONSTITUTION.md` Rule 01; `SKILL_SPEC.md` constitution binding | `run.sh validate` + docs review | Met |
| R02 | 必须提供 allowed module boundary | all pipelines input contract (`allowed_module_root`) | `ops_guard.py --allowed-root` | Met |
| R03 | 禁止改 `/sys,/error,/util,/vote` | constitution Rule 03; pipeline `forbidden`; super skill `boundary_policy.forbidden_paths` | `ops_guard.py` forbidden-path check | Met |
| R04 | 事实优先，改前扫描 | constitution Rule 05; super skill `fact_policy.require_scan_before_change` | pipeline Step1 scan-first + `ops_guard_report.json` evidence note | Met |
| R05 | 不确定必须请求补充，禁止臆测 | constitution Rule 05; super skill `fact_policy.unknown_requires_user` and prompt template clause | pipeline forbidden default | Met |
| R06 | 依赖策略顺序 compat > self-contained > minimal-invasive | constitution Rule 04; super skill `decision_policy.dependency_strategy_order` | route A/B output in scan step | Met |
| R07 | 改动前树状影响分析 | constitution Rule 06; super skill mandatory artifact `A*_impact_tree.md` | pipeline acceptance clauses | Met |
| R08 | 高风险报警与升级 | constitution Rule 07; super skill `risks[]` contract | release/governance steps | Met |
| R09 | 自监控回圈检测 | constitution Rule 08; super skill `self_monitor_policy.loop_detection` | `ops_guard.py` loop-risk signal section | Met |
| R10 | 回圈触发自动回退 | constitution Rule 09; super skill `self_monitor_policy.auto_rollback_on_loop` | mandatory `A*_rollback_plan.md` | Met |
| R11 | SQL 优先可移植 | constitution Rule 10; super skill `sql_policy.prefer_portable_sql` | SQL pipelines | Met |
| R12 | 不可通用时提供 Oracle+MySQL 双版本 | constitution Rule 11; super skill `sql_policy.dual_sql_when_needed` | SQL mode acceptance | Met |
| R13 | 作业收尾：README/台账/清理 | constitution Rule 13; super skill mandatory artifacts `change_ledger/cleanup_report` | docs step in each pipeline | Met |
| R14 | 回滚说明必须交付 | constitution Rule 15; super skill mandatory `A*_rollback_plan.md` | release/docs closure | Met |
| R15 | 规范可执行化（闸门/工具/pipeline） | constitution + pipeline alignment + super skill + `ops_guard.py` | `validate`, `run`, `ops_guard`, `merged_guard` | Met |
| R16 | bypass 环境变量治理 | `HONGZHI_COMPANY_CONSTITUTION.md` Rule 16; `pipeline_skill_creator.md` NOTE | change ledger audit + team review | Met |
| R17 | Plugin governance 不退化（disabled-by-default + deny/allow/token） | `HONGZHI_COMPANY_CONSTITUTION.md` Rule 17; `hongzhi_plugin.py` governance gate | regression Phase18/19 | Met |
| R18 | Capability Registry + Smart Incremental + 禁用态不写 state | `HONGZHI_COMPANY_CONSTITUTION.md` Rule 18; `hongzhi_plugin.py`; `hongzhi_ai_kit/capability_store.py`; `hongzhi_ai_kit/paths.py` | regression Phase20/21/22 | Met |
| R19 | Plugin packaging + agent contract v4 (`HONGZHI_CAPS`, capabilities.jsonl, module/console entry) | `pyproject.toml`; `hongzhi_ai_kit/cli.py`; `hongzhi_plugin.py`; `PLUGIN_RUNNER.md` | regression Phase23 + validate | Met |

## File Mapping (Core)

- Constitution: `prompt-dsl-system/00_conventions/HONGZHI_COMPANY_CONSTITUTION.md`
- Skill spec binding: `prompt-dsl-system/00_conventions/SKILL_SPEC.md`
- Universal skill: `prompt-dsl-system/05_skill_registry/skills/universal/skill_hongzhi_universal_ops.yaml`
- Pipelines:
  - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md`
  - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_ownercommittee_audit_fix.md`
  - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_bpmn_state_audit_testgen.md`
  - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_db_delivery_batch_and_runbook.md`
  - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_bugfix_min_scope_with_tree.md`
  - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_skill_creator.md`
  - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_project_bootstrap.md`
  - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_skill_promote.md`
  - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_module_migration.md`
  - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_plugin_discover.md`
- Conventions:
  - `prompt-dsl-system/00_conventions/CPP_STYLE_NAMING.md`
  - `prompt-dsl-system/00_conventions/SQL_COMPAT_STRATEGY.md`
  - `prompt-dsl-system/00_conventions/PROJECT_PROFILE_SPEC.md`
  - `prompt-dsl-system/00_conventions/MODULE_PROFILE_SPEC.md` (3-layer: declared + discovered + merge + multi-root + Layer2R + Layer2S)
- Templates:
  - `prompt-dsl-system/05_skill_registry/templates/skill_template/` (skill.yaml.template + references/scripts/assets READMEs)
- Resource Convention: SKILL_SPEC.md §Bundled Resources Convention + §Progressive Disclosure + §NavIndex Output Format
- Skill Status Lifecycle: SKILL_SPEC.md §Skill Status Lifecycle (staging/deployed/deprecated + promotion flow)
- Tools:
  - `prompt-dsl-system/tools/ops_guard.py` (+VCS strict: HONGZHI_GUARD_REQUIRE_VCS + multi-path + robust ignore patterns)
  - `prompt-dsl-system/tools/pipeline_runner.py`
  - `prompt-dsl-system/tools/merged_guard.py`
  - `prompt-dsl-system/tools/skill_template_audit.py` (--scope, --fail-on-empty, registry↔fs consistency)
  - `prompt-dsl-system/tools/pipeline_contract_lint.py` (--fail-on-empty, module_root + NavIndex + profile template check + strict TODO reject + identity hints)
  - `prompt-dsl-system/tools/golden_path_regression.sh` (41 checks: Phase1-8 core + Phase9-14 discovery + Phase15-19 plugin runner & governance + Phase20-22 capability registry/smart reuse/no-state-write + Phase23 package/entry/contract checks)
  - `prompt-dsl-system/tools/module_profile_scanner.py` (Layer2 + fingerprint + multi-root + concurrent + incremental + --out-root/--read-only/--workspace-root)
  - `prompt-dsl-system/tools/module_roots_discover.py` (Layer2R + identity hints + structure fallback + optional --module-key + --out-root/--read-only)
  - `prompt-dsl-system/tools/structure_discover.py` v2 (Layer2S + endpoint v2 + per-file incremental cache + --out-root/--read-only/--workspace-root)
  - `prompt-dsl-system/tools/cross_project_structure_diff.py` v2 (endpoint signature comparison + --read-only)
  - `prompt-dsl-system/tools/auto_module_discover.py` (module discovery without --module-key + scoring + --read-only)
  - `prompt-dsl-system/tools/hongzhi_plugin.py` (v4-compatible runner: discover/diff/profile/migrate/status/clean, governance, smart incremental, `HONGZHI_CAPS`, capabilities.jsonl, capability index/latest/run_meta)
  - `prompt-dsl-system/tools/hongzhi_ai_kit` (installable package wrapper + module entry)
  - `prompt-dsl-system/tools/hongzhi_ai_kit/capability_store.py` (atomic capability index persistence helpers)
  - `prompt-dsl-system/tools/hongzhi_ai_kit/paths.py` (workspace/global-state root resolution)
  - `pyproject.toml` (editable install + console entry: `hongzhi-ai-kit`)
  - `prompt-dsl-system/tools/PLUGIN_RUNNER.md` (plugin runner documentation)
  - `prompt-dsl-system/tools/README.md`
