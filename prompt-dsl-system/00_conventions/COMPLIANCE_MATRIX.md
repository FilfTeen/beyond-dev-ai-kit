# Compliance Matrix (Original 15 Requirements + R16~R45 -> Current Implementation)

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
| R20 | Release-grade build + version triplet contract + gitignore pollution guard | `hongzhi_plugin.py`; `golden_path_regression.sh` Phase24; `.gitignore`; `PLUGIN_RUNNER.md` | regression Phase24 + validate(strict) | Met |
| R21 | Governance v3 (token ttl/scope + symlink hardening) + limits exit20 + status->decide->discover pipeline gate | `hongzhi_plugin.py`; `pipeline_plugin_discover.md`; `skill_governance_plugin_status.yaml`; `golden_path_regression.sh` Phase25 | regression Phase25 + validate(strict) | Met |
| R22 | Calibration layer explainability + strict needs_human_hint gate (exit21) + workspace-only hints | `calibration_engine.py`; `hongzhi_plugin.py`; `golden_path_regression.sh` Phase26; `PLUGIN_RUNNER.md` | regression Phase26 + validate(strict) | Met |
| R23 | Hint Loop + Layout Adapters v1 + smart reuse validation + governance zero-write carryover | `hongzhi_plugin.py`; `layout_adapters.py`; `pipeline_plugin_discover.md`; `skill_governance_plugin_discover_with_hints.yaml`; `golden_path_regression.sh` Phase27; `PLUGIN_RUNNER.md` | regression Phase27 + validate(strict) | Met |
| R24 | Hint assetization profile_delta bundle + apply verification (path/inline JSON) + token hint scope gate + strict exits 22/23 | `hongzhi_ai_kit/hint_bundle.py`; `hongzhi_plugin.py`; `golden_path_regression.sh` Phase28; `PLUGIN_RUNNER.md` | regression Phase28 + validate(strict) | Met |
| R25 | Capability Index Federation: federated index store + index CLI(list/query/explain) + federated scope gate strict exit24/non-strict warn + governance deny zero-write carryover | `hongzhi_ai_kit/federated_store.py`; `hongzhi_plugin.py`; `golden_path_regression.sh` Phase29; `PLUGIN_RUNNER.md` | regression Phase29 + validate(strict) | Met |
| R26 | Round24 hardening: status/index zero-touch, read-only guard full snapshot, policy parse fail-closed (exit13), machine-line path safety, jsonl concurrency, discover IO stats + hint effectiveness, composed endpoint extraction | `hongzhi_ai_kit/paths.py`; `hongzhi_plugin.py`; `hongzhi_ai_kit/capability_store.py`; `hongzhi_ai_kit/federated_store.py`; `structure_discover.py`; `golden_path_regression.sh` Phase30; `PLUGIN_RUNNER.md` | regression Phase30 + validate(strict) | Met |
| R27 | Round25 unified scan graph middle layer + cross-command reuse (discover/profile/diff) + strict mismatch gate (exit25) + governance zero-write carryover | `scan_graph.py`; `hongzhi_plugin.py`; `module_profile_scanner.py`; `cross_project_structure_diff.py`; `golden_path_regression.sh` Phase31; `PLUGIN_RUNNER.md` | regression Phase31 + validate(strict) | Met |
| R28 | Round26 additive contract hardening: scan_graph schema_version+producer_versions+graph_fingerprint, strict mismatch reason/detail emission, machine-line `json='...'` payload, profile/diff default no-rescan reuse, governance zero-write carryover, read-only full-snapshot with limits | `scan_graph.py`; `hongzhi_plugin.py`; `golden_path_regression.sh` Phase32; `PLUGIN_RUNNER.md` | regression Phase32 + validate(strict) | Met |
| R29 | Round27 machine-line json roundtrip + deterministic ordering + mismatch enum/suggestion + read-command zero-touch probe hardening + CLI `--machine-json` (env override) | `hongzhi_plugin.py`; `hongzhi_ai_kit/paths.py`; `golden_path_regression.sh` Phase33; `PLUGIN_RUNNER.md` | regression Phase33 + validate(strict) | Met |
| R30 | Round28 machine-line contract schema + zero-dependency validator + regression hard-gate (discover/gov-block/exit25/additive schema guard) | `contract_schema_v1.json`; `contract_validator.py`; `golden_path_regression.sh` Phase34; `PLUGIN_RUNNER.md` | regression Phase34 + validate(strict) | Met |
| R31 | Round29 company-scope optional hard gate + machine-line scope signal + governance skill lifecycle convergence (deployed) | `hongzhi_plugin.py`; `skills.json`; `golden_path_regression.sh` Phase35; `PLUGIN_RUNNER.md` | regression Phase35 + validate(strict) | Met |
| R32 | 项目技术栈知识库：按项目扫描建档（declared + discovered）并可审计复核 | constitution Rule 21; `PROJECT_TECH_STACK_SPEC.md`; `project_stacks/**`; `project_stack_scanner.py`; `pipeline_project_stack_bootstrap.md` | `run.sh validate` + scanner run evidence | Met |
| R33 | 产品经理链路：需求澄清→流程切片→接口/数据/验收→低保真原型 | constitution Rule 22; `pipeline_requirement_to_prototype.md`; `skill_hongzhi_universal_ops.yaml` | `run.sh validate` + pipeline_contract_lint | Met |
| R34 | 个人开发范式落地（C++ 对齐且团队优先） | constitution Rule 23; `PERSONAL_DEV_STANDARD.md`; `CPP_STYLE_NAMING.md` | docs review + `run.sh validate` | Met |
| R35 | 套件主线约束：beyond-dev-ai-kit 优化任务默认 kit-only，禁止外部业务仓库写入 | constitution Rule 24; toolkit path boundary policy | `run.sh validate` + scope review | Met |
| R36 | 套件自检门禁：重大升级前必须运行质量评分并据此给出升级路线 | constitution Rule 25; `KIT_QUALITY_MODEL.md`; `kit_selfcheck.py`; `pipeline_kit_self_upgrade.md`; `skill_governance_audit_kit_quality.yaml` | `run.sh validate` + `kit_selfcheck.py` | Met |
| R37 | agent 主动感知：selfcheck 需输出机器可读 `KIT_CAPS` 指针行 | constitution Rule 26; `kit_selfcheck.py`; `run.sh selfcheck` | `./prompt-dsl-system/tools/run.sh selfcheck -r .` | Met |
| R38 | 统一自升级入口：`run.sh self-upgrade` 注入默认 module_path(仓库根)/pipeline，避免参数漂移 | constitution Rule 27; `run.sh`; `pipeline_kit_self_upgrade.md` | `./prompt-dsl-system/tools/run.sh self-upgrade -r .` | Met |
| R39 | 严格自升级门禁链：selfcheck(contract)→selfcheck_gate→lint→audit→validate(strict) fail-fast | constitution Rule 28; `run.sh --strict-self-upgrade`; `contract_validator.py`; `kit_selfcheck_gate.py`; `pipeline_contract_lint.py`; `skill_template_audit.py` | `./prompt-dsl-system/tools/run.sh self-upgrade -r . --strict-self-upgrade` | Met |
| R40 | 合约演进可兼容：schema v2 对 v1 进行 additive guard 校验，默认优先最新 schema | constitution Rule 29; `contract_schema_v2.json`; `contract_schema_v1.json`; `CONTRACT_COMPATIBILITY_STRATEGY.md`; `contract_validator.py` | `contract_validator.py --schema v2 --baseline-schema v1` | Met |
| R41 | 自升级收尾标准化：A3 模板化交付 + 合约样例回放基线 | constitution Rule 30; `tools/artifacts/templates/kit_self_upgrade/**`; `tools/contract_samples/**`; `golden_path_regression.sh` Phase36 | `bash prompt-dsl-system/tools/contract_samples/replay_contract_samples.sh --repo-root .` | Met |
| R42 | validate 默认后置闸门：contract replay + template guard，失败即失败 | constitution Rule 31; `run.sh`; `kit_self_upgrade_template_guard.py`; `contract_samples/replay_contract_samples.sh`; `golden_path_regression.sh` Phase37 | `./prompt-dsl-system/tools/run.sh validate -r .` | Met |
| R43 | 可观测性强化：post-gate 结果必须汇总进 health_report 独立 section | constitution Rule 32; `health_post_validate_sync.py`; `run.sh`; `golden_path_regression.sh` Phase38 | `./prompt-dsl-system/tools/run.sh validate -r .` + `health_report.json` | Met |
| R44 | 严格自升级质量阈值门禁：selfcheck 分数/等级/low维度需达标，否则阻断 | constitution Rule 33; `run.sh --strict-self-upgrade`; `kit_selfcheck_gate.py`; `KIT_QUALITY_MODEL.md`; `golden_path_regression.sh` Phase40 | `./prompt-dsl-system/tools/run.sh self-upgrade -r . --strict-self-upgrade` | Met |
| R45 | 严格自升级维度契约门禁：required dimensions + dimension_count 一致性不满足即阻断 | constitution Rule 34; `run.sh --strict-self-upgrade`; `kit_selfcheck_gate.py`; `KIT_QUALITY_MODEL.md`; `golden_path_regression.sh` Phase41 | `./prompt-dsl-system/tools/run.sh self-upgrade -r . --strict-self-upgrade` | Met |

## File Mapping (Core)

- Constitution: `prompt-dsl-system/00_conventions/HONGZHI_COMPANY_CONSTITUTION.md`
- Skill spec binding: `prompt-dsl-system/00_conventions/SKILL_SPEC.md`
- Universal skill: `prompt-dsl-system/05_skill_registry/skills/universal/skill_hongzhi_universal_ops.yaml`
- Governance selfcheck skill: `prompt-dsl-system/05_skill_registry/skills/governance/skill_governance_audit_kit_quality.yaml`
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
  - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_project_stack_bootstrap.md`
  - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_requirement_to_prototype.md`
  - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md`
- Conventions:
  - `prompt-dsl-system/00_conventions/CPP_STYLE_NAMING.md`
  - `prompt-dsl-system/00_conventions/PERSONAL_DEV_STANDARD.md`
  - `prompt-dsl-system/00_conventions/KIT_QUALITY_MODEL.md`
  - `prompt-dsl-system/00_conventions/CONTRACT_COMPATIBILITY_STRATEGY.md`
  - `prompt-dsl-system/00_conventions/SQL_COMPAT_STRATEGY.md`
  - `prompt-dsl-system/00_conventions/PROJECT_PROFILE_SPEC.md`
  - `prompt-dsl-system/00_conventions/PROJECT_TECH_STACK_SPEC.md`
  - `prompt-dsl-system/00_conventions/MODULE_PROFILE_SPEC.md` (3-layer: declared + discovered + merge + multi-root + Layer2R + Layer2S)
- Templates:
  - `prompt-dsl-system/05_skill_registry/templates/skill_template/` (skill.yaml.template + references/scripts/assets READMEs)
- Resource Convention: SKILL_SPEC.md §Bundled Resources Convention + §Progressive Disclosure + §NavIndex Output Format
- Skill Status Lifecycle: SKILL_SPEC.md §Skill Status Lifecycle (staging/deployed/deprecated + promotion flow)
- Tools:
  - `prompt-dsl-system/tools/ops_guard.py` (+VCS strict: HONGZHI_GUARD_REQUIRE_VCS + multi-path + robust ignore patterns)
  - `prompt-dsl-system/tools/pipeline_runner.py`
  - `prompt-dsl-system/tools/project_stack_scanner.py` (project-level stack scanner: declared/discovered KB bootstrap with evidence output)
  - `prompt-dsl-system/tools/kit_selfcheck.py` (kit quality dimension scorecard + recommendations)
  - `prompt-dsl-system/tools/kit_selfcheck_gate.py` (strict self-upgrade gate for score/level/required-dimensions/dimension_count contract)
  - `prompt-dsl-system/tools/contract_schema_v2.json` (machine-line contract v2, additive over v1)
  - `prompt-dsl-system/tools/contract_validator.py` (default prefer latest schema + additive baseline guard)
  - `prompt-dsl-system/tools/contract_samples/` (replayable machine-line samples + replay script)
  - `prompt-dsl-system/tools/artifacts/templates/kit_self_upgrade/` (A3 closure templates for self-upgrade)
  - `prompt-dsl-system/tools/kit_self_upgrade_template_guard.py` (A3 template integrity guard)
  - `prompt-dsl-system/tools/health_post_validate_sync.py` (sync post-gate results into health_report section)
  - `prompt-dsl-system/tools/merged_guard.py`
  - `prompt-dsl-system/tools/skill_template_audit.py` (--scope, --fail-on-empty, registry↔fs consistency)
  - `prompt-dsl-system/tools/pipeline_contract_lint.py` (--fail-on-empty, module_root + NavIndex + profile template check + strict TODO reject + identity hints)
- `prompt-dsl-system/tools/golden_path_regression.sh` (132 checks: Phase1-8 core + Phase9-14 discovery + Phase15-19 plugin runner & governance + Phase20-22 capability registry/smart reuse/no-state-write + Phase23 package/entry/contract + uninstalled install-hint checks + Phase24 release build/version triplet/gitignore/governance-no-write + Phase25 token ttl/scope/symlink/limits/capability-index-gating/pipeline decision chain + Phase26 calibration strict/non-strict/output/schema checks + Phase27 hint-loop/apply-hints/layout adapters/reuse validation/governance no-write/index-hint-metrics checks + Phase28 profile_delta hint bundle schema/apply/expiry/scope/index gating checks + Phase29 federated index write/query/explain/scope gating/zero-write checks + Phase30 hardening checks for zero-touch/full-snapshot/fail-closed/path-safe/concurrency/io-stats/endpoint/hint-effectiveness + Phase31 unified scan graph/cross-command reuse/strict mismatch checks + Phase32 additive contract/machine-json/reuse-no-rescan/full-snapshot-limits checks + Phase33 machine-json roundtrip/no-newline, deterministic artifacts/modules ordering, mismatch enum/suggestion, status/index zero-touch probe checks + Phase34 contract schema v1/v2 + validator + additive guard checks + Phase35 company-scope gate and governance skill lifecycle checks + Phase36 strict self-upgrade preflight + contract sample replay + A3 template baseline checks + Phase37 validate default post-gates checks + Phase38 health_report post-gate section checks + Phase39 runbook post-gate fail-first checks + Phase40 selfcheck quality threshold gate checks + Phase41 selfcheck dimension contract checks)
  - `prompt-dsl-system/tools/module_profile_scanner.py` (Layer2 + fingerprint + multi-root + concurrent + incremental + --out-root/--read-only/--workspace-root)
  - `prompt-dsl-system/tools/module_roots_discover.py` (Layer2R + identity hints + structure fallback + optional --module-key + --out-root/--read-only)
  - `prompt-dsl-system/tools/structure_discover.py` v2 (Layer2S + endpoint v2 + per-file incremental cache + --out-root/--read-only/--workspace-root)
  - `prompt-dsl-system/tools/cross_project_structure_diff.py` v2 (endpoint signature comparison + --read-only)
  - `prompt-dsl-system/tools/auto_module_discover.py` (module discovery without --module-key + scoring + --read-only)
  - `prompt-dsl-system/tools/hongzhi_plugin.py` (v4-compatible runner: discover/diff/profile/migrate/status/clean, governance, smart incremental, `HONGZHI_CAPS`, capabilities.jsonl, capability index/latest/run_meta)
  - `prompt-dsl-system/tools/calibration_engine.py` (discover calibration, reasons enum, confidence tiering, workspace hint/report emission)
- `prompt-dsl-system/tools/layout_adapters.py` (layout adapters v1 for multi-module/non-standard Java root detection)
- `prompt-dsl-system/tools/scan_graph.py` (Unified Scan Graph v1 single-walk index + cache + io stats)
- `prompt-dsl-system/tools/hongzhi_ai_kit/hint_bundle.py` (profile_delta hint bundle build/load/verify primitives)
- `prompt-dsl-system/tools/hongzhi_ai_kit/federated_store.py` (federated index atomic persistence + query ranking helpers)
  - `prompt-dsl-system/tools/hongzhi_ai_kit` (installable package wrapper + module entry)
  - `prompt-dsl-system/tools/hongzhi_ai_kit/capability_store.py` (atomic capability index persistence helpers)
  - `prompt-dsl-system/tools/hongzhi_ai_kit/paths.py` (workspace/global-state root resolution)
  - `pyproject.toml` (editable install + console entry: `hongzhi-ai-kit`)
  - `prompt-dsl-system/tools/PLUGIN_RUNNER.md` (plugin runner documentation)
  - `prompt-dsl-system/tools/README.md`
