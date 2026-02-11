# FACT BASELINE (prompt-dsl-system)

Generated at: 2026-02-10 (local)
Scope: `prompt-dsl-system/**`

## 1) Current Skills Baseline

- Active registry file: `prompt-dsl-system/05_skill_registry/skills.json`
- Active skills count: `1`
- Domain distribution: `universal=1`
- Universal/super skill status: `present`
  - `skill_hongzhi_universal_ops` (modes: sql/code/process/frontend/release/governance/docs/meta)
  - meta mode: supports template-based skill creation + progressive disclosure
- Skill templates: `prompt-dsl-system/05_skill_registry/templates/skill_template/`
  - Files: `skill.yaml.template`, `references/README.template`, `scripts/README.template`, `assets/README.template`
- Deprecated skills status:
  - archived files under `prompt-dsl-system/05_skill_registry/deprecated/skills/**`
  - current archived count: `28`

## 2) Current Pipelines Baseline

- Pipeline files (`pipeline_*.md`) count: `9`
- `pipeline_sql_oracle_to_dm8.md`: `4` steps, all reference `skill_hongzhi_universal_ops`
- `pipeline_ownercommittee_audit_fix.md`: `5` steps, all reference `skill_hongzhi_universal_ops`
- `pipeline_bpmn_state_audit_testgen.md`: `5` steps, all reference `skill_hongzhi_universal_ops`
- `pipeline_db_delivery_batch_and_runbook.md`: `3` steps, all reference `skill_hongzhi_universal_ops`
- `pipeline_bugfix_min_scope_with_tree.md`: `4` steps, all reference `skill_hongzhi_universal_ops`
- `pipeline_skill_creator.md`: `5` steps, all reference `skill_hongzhi_universal_ops` (modes: governance/meta/meta/meta/docs)
- `pipeline_project_bootstrap.md`: `5` steps, all reference `skill_hongzhi_universal_ops` — batch skill generation + profile input
- `pipeline_skill_promote.md`: `3` steps, all reference `skill_hongzhi_universal_ops` — staging→deployed promotion + mandatory ledger
- `pipeline_module_migration.md`: `6` steps, all reference `skill_hongzhi_universal_ops` — single-module migration assembly line + materialize_skills switch

## 3) Current Tools Boundary

- `run.sh`: stable wrapper (`/usr/bin/python3`) for `pipeline_runner.py`; supports `HONGZHI_VALIDATE_STRICT=1` env var for anti-false-green
- `pipeline_runner.py`:
  - `list/validate/run`
  - validates registry + pipelines
  - parses YAML blocks in pipeline markdown
  - generates `run_plan.yaml` and `validate_report.json`
  - supports company profile default injection (`schema_strategy/execution_tool/require_precheck_gate`)
- `merged_guard.py`: merged/batch SQL integrity gate for trace delivery
- `path_diff_guard.py`: path diff + violation detection + VCS strict fail (HONGZHI_VALIDATE_STRICT/HONGZHI_GUARD_REQUIRE_VCS)
- `ops_guard.py`: module boundary + forbidden-path + loop-risk + VCS metadata strict check (HONGZHI_GUARD_REQUIRE_VCS)
- `skill_template_audit.py`: post-validate audit (placeholder + schema + registry↔fs consistency + --scope + --fail-on-empty)
- `pipeline_contract_lint.py`: post-validate lint (module_root + NavIndex + --fail-on-empty + profile template check + strict TODO reject)
- `golden_path_regression.sh`: end-to-end regression (validate→bootstrap→validate→promote→validate + migration smoke + profile smoke + guard strict)
- `module_profile_scanner.py`: generates discovered profile (Layer2) by scanning filesystem + grep patterns + fingerprint

## 4) Conventions Documents

- `HONGZHI_COMPANY_CONSTITUTION.md`: 16 rules, company-domain governance
- `SKILL_SPEC.md`: YAML schema, registry contract, trace parameters, template generation, bundled resources, progressive disclosure + NavIndex, skill status lifecycle (staging/deployed/deprecated)
- `COMPLIANCE_MATRIX.md`: 15 requirements mapped to implementation
- `ROLLBACK_INSTRUCTIONS.md`: rollback procedure
- `FACT_BASELINE.md`: this document
- `CPP_STYLE_NAMING.md`: C++ style naming conventions for Java8+SpringBoot
- `SQL_COMPAT_STRATEGY.md`: SQL dual-stack delivery specification
- `PROJECT_PROFILE_SPEC.md`: project profile input contract for pipeline_project_bootstrap
- `MODULE_PROFILE_SPEC.md`: three-layer module profile model (declared + discovered + merge rules)
- `SKILL_SPEC.md` extended sections:
  - Skill Template Generation Contract
  - Bundled Resources Convention (references/scripts/assets)
  - Progressive Disclosure (TOC-first, navigate on demand)

## 5) Trace/Handoff Norm Status

- `context_id/trace_id/input_artifact_refs` rule exists in `SKILL_SPEC.md`
- Current pipelines already include `context_id/trace_id/input_artifact_refs` in each step

## 6) 15-Point Requirement Check (Fact-Driven)

Note: the 15 points below are mapped from the user-provided original requirement set for company-domain governance.

| ID | Requirement (from original 15 set) | Baseline status | Evidence |
|---|---|---|---|
| R01 | Company-domain isolation (only for hongzhi company tasks) | Met | `CONSTITUTION.md` Rule 01 scope binding; skill prompt company-scoped |
| R02 | Strict module boundary (allowed root required before editing) | Met | All pipelines require `allowed_module_root`; `ops_guard.py --allowed-root` enforced |
| R03 | Default forbidden paths (`/sys,/error,/util,/vote`) hard constraint | Met | `CONSTITUTION.md` Rule 03; skill `boundary_policy.forbidden_paths`; `ops_guard.py` |
| R04 | Fact-first: scan before change | Met | Skill `fact_policy.require_scan_before_change=true`; pipeline Step1 scan-first |
| R05 | Unknown facts must require user confirmation | Met | Skill `fact_policy.unknown_requires_user=true`; prompt template clause |
| R06 | Dependency strategy order `compat > self-contained > minimal-invasive` | Met | Skill `decision_policy.dependency_strategy_order`; `CONSTITUTION.md` Rule 04 |
| R07 | Tree impact analysis required before change | Met | Skill mandatory artifact `A*_impact_tree.md`; `CONSTITUTION.md` Rule 06 |
| R08 | High-risk escalation trigger | Met | Skill `risks[]` contract; `CONSTITUTION.md` Rule 07 |
| R09 | Self-monitor loop detection (`same file >3`, `same failure >2`) | Met | Skill `self_monitor_policy.loop_detection=true`; `CONSTITUTION.md` Rule 08 |
| R10 | Auto rollback on loop | Met | Skill `self_monitor_policy.auto_rollback_on_loop=true`; `CONSTITUTION.md` Rule 09 |
| R11 | SQL portable first | Met | Skill `sql_policy.prefer_portable_sql=true`; `SQL_COMPAT_STRATEGY.md` |
| R12 | Dual SQL output when non-portable (Oracle+MySQL) | Met | Skill `sql_policy.dual_sql_when_needed`; `SQL_COMPAT_STRATEGY.md` |
| R13 | Job closure: README/dir doc update + change log + cleanup report | Met | Skill mandatory artifacts; pipeline closure steps; `CONSTITUTION.md` Rule 13 |
| R14 | Rollback plan artifact mandatory | Met | Skill mandatory `A*_rollback_plan.md`; `CONSTITUTION.md` Rule 15; `ROLLBACK_INSTRUCTIONS.md` |
| R15 | Enforceable gates/tools + compliance matrix mapping | Met | `ops_guard.py`, `merged_guard.py`, `run.sh validate`; `COMPLIANCE_MATRIX.md` |

## 7) Baseline Validate Gate

- Command: `./prompt-dsl-system/tools/run.sh validate --repo-root .`
- Result: `Errors=0`, `Warnings=0`
- Baseline gate status: `PASS`
