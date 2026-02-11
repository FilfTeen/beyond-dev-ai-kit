# FACT BASELINE (prompt-dsl-system)

Generated at: 2026-02-10 (local)
Scope: `prompt-dsl-system/**`

## 1) Current Skills Baseline

- Active registry file: `prompt-dsl-system/05_skill_registry/skills.json`
- Active skills count: `3`
- Domain distribution: `universal=1, governance=2`
- Universal/super skill status: `present`
  - `skill_hongzhi_universal_ops` (modes: sql/code/process/frontend/release/governance/docs/meta)
  - meta mode: supports template-based skill creation + progressive disclosure
- Governance plugin skills:
  - `skill_governance_plugin_discover` (staging)
  - `skill_governance_plugin_runner` (staging, contract v4-aware)
- Skill templates: `prompt-dsl-system/05_skill_registry/templates/skill_template/`
  - Files: `skill.yaml.template`, `references/README.template`, `scripts/README.template`, `assets/README.template`
- Deprecated skills status:
  - archived files under `prompt-dsl-system/05_skill_registry/deprecated/skills/**`
  - current archived count: `28`

## 2) Current Pipelines Baseline

- Pipeline files (`pipeline_*.md`) count: `10`
- `pipeline_sql_oracle_to_dm8.md`: `4` steps, all reference `skill_hongzhi_universal_ops`
- `pipeline_ownercommittee_audit_fix.md`: `5` steps, all reference `skill_hongzhi_universal_ops`
- `pipeline_bpmn_state_audit_testgen.md`: `5` steps, all reference `skill_hongzhi_universal_ops`
- `pipeline_db_delivery_batch_and_runbook.md`: `3` steps, all reference `skill_hongzhi_universal_ops`
- `pipeline_bugfix_min_scope_with_tree.md`: `4` steps, all reference `skill_hongzhi_universal_ops`
- `pipeline_skill_creator.md`: `5` steps, all reference `skill_hongzhi_universal_ops` (modes: governance/meta/meta/meta/docs)
- `pipeline_project_bootstrap.md`: `5` steps, all reference `skill_hongzhi_universal_ops` — batch skill generation + profile input
- `pipeline_skill_promote.md`: `3` steps, all reference `skill_hongzhi_universal_ops` — staging→deployed promotion + mandatory ledger
- `pipeline_module_migration.md`: `7` steps (Step0–Step5 + acceptance), all reference `skill_hongzhi_universal_ops` — single-module migration assembly line + materialize_skills switch + Step0 auto-discovery
- `pipeline_plugin_discover.md`: `3` steps (status preflight → discover → capabilities read/suggestion), references `skill_governance_plugin_runner`

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
- `ops_guard.py`: module boundary + forbidden-path + loop-risk + VCS metadata strict check (HONGZHI_GUARD_REQUIRE_VCS) + multi-path + ignore patterns
- `skill_template_audit.py`: post-validate audit (placeholder + schema + registry↔fs consistency + --scope + --fail-on-empty)
- `pipeline_contract_lint.py`: post-validate lint (module_root + NavIndex + --fail-on-empty + profile template check + strict TODO reject + identity hints)
- `golden_path_regression.sh`: end-to-end regression (41 checks: Phase1-8 core + Phase9-14 discovery + Phase15-19 plugin runner/governance + Phase20-22 capability registry/smart reuse/no-state-write + Phase23 packaging/contract v4)
- `module_profile_scanner.py`: generates discovered profile (Layer2) — scanning + grep + fingerprint + multi-root + concurrent + incremental + `--out-root`/`--read-only`/`--workspace-root`
- `module_roots_discover.py`: auto-discovers module roots from identity hints + structure fallback + optional `--module-key` (auto-discover) + `--out-root`/`--read-only` (Layer2R)
- `structure_discover.py` v2: auto-identifies module structure — endpoint v2, per-file incremental cache, `--out-root`/`--read-only`/`--workspace-root` (Layer2S)
- `cross_project_structure_diff.py` v2: compares endpoint signatures, reports added/removed/changed, `--read-only`
- `auto_module_discover.py`: discovers module candidates without `--module-key` — package prefix clustering, scoring, top-k, `--read-only`
- `hongzhi_plugin.py`: v4 contract-capable runner — discover/diff/profile/migrate/status/clean, snapshot-diff read-only contract, governance (enabled/deny/allow/token), smart incremental, capability registry, `HONGZHI_CAPS` line, capabilities.jsonl journal
- `hongzhi_ai_kit`: installable python package wrapper with module/console entry support
- `pyproject.toml` (repo root): packaging metadata + console_scripts (`hongzhi-ai-kit`, `hzkit`, `hz`)
- `PLUGIN_RUNNER.md`: plugin runner documentation (install, governance, v3/v4 contract, workspace/global state)

## 4) Conventions Documents

- `HONGZHI_COMPANY_CONSTITUTION.md`: 18 rules, company-domain governance
- `SKILL_SPEC.md`: YAML schema, registry contract, trace parameters, template generation, bundled resources, progressive disclosure + NavIndex, skill status lifecycle (staging/deployed/deprecated)
- `COMPLIANCE_MATRIX.md`: 15 requirements mapped to implementation
- `ROLLBACK_INSTRUCTIONS.md`: rollback procedure
- `FACT_BASELINE.md`: this document
- `CPP_STYLE_NAMING.md`: C++ style naming conventions for Java8+SpringBoot
- `SQL_COMPAT_STRATEGY.md`: SQL dual-stack delivery specification
- `PROJECT_PROFILE_SPEC.md`: project profile input contract for pipeline_project_bootstrap
- `MODULE_PROFILE_SPEC.md`: three-layer module profile model (declared + discovered + merge rules + multi-root + Layer2R)
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

## 7) Capability Registry & Smart Incremental (R16)

- Capability registry global root is separated from per-run workspace root.
- New global files:
  - `capability_index.json` (cross-project capability summary)
  - `<fingerprint>/latest.json` (latest successful run pointer)
  - `<fingerprint>/runs/<run_id>/run_meta.json` (auditable run metadata)
- Smart incremental flags available for `discover/profile/diff/migrate`:
  - `--smart`
  - `--smart-max-age-seconds`
  - `--smart-min-cache-hit`
  - `--smart-max-fingerprint-drift`
- Governance non-degradation:
  - disabled by default remains enforced (exit 10/11/12)
  - denied runs do not write global capability state
  - business repo remains read-only by default, guarded by snapshot-diff (exit 3 on mutation)

## 8) Baseline Validate Gate

- Command: `./prompt-dsl-system/tools/run.sh validate --repo-root .`
- Result: `Errors=0`, `Warnings=0`
- Baseline gate status: `PASS`

## 9) Packaging & Contract v4 (R17)

- Packaging:
  - `pip install -e .` installs `hongzhi_ai_kit` module and `hongzhi-ai-kit` console entry.
  - Root execution no longer requires manual `PYTHONPATH` editing after install.
- Agent contract v4 additions:
  - stdout `HONGZHI_CAPS <abs_path_to_capabilities.json>`
  - workspace append-only `capabilities.jsonl` run summary journal
  - blocked governance runs emit machine-readable `HONGZHI_GOV_BLOCK ...` and write no capabilities/state artifacts
