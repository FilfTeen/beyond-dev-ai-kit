# FACT BASELINE (prompt-dsl-system)

Generated at: 2026-02-12 (local)
Scope: `prompt-dsl-system/**`

## 1) Current Skills Baseline

- Active registry file: `prompt-dsl-system/05_skill_registry/skills.json`
- Active skills count: `6`
- Domain distribution: `universal=1, governance=5`
- Universal/super skill status: `present`
  - `skill_hongzhi_universal_ops` (modes: sql/code/process/frontend/release/governance/docs/meta)
  - meta mode: supports template-based skill creation + progressive disclosure
- Governance plugin skills:
  - `skill_governance_plugin_discover` (deployed)
  - `skill_governance_plugin_runner` (deployed, contract v4-aware)
  - `skill_governance_plugin_status` (deployed, governance preflight only)
  - `skill_governance_plugin_discover_with_hints` (deployed, hint-loop aware discover orchestration)
  - `skill_governance_audit_kit_quality` (deployed, kit quality scorecard and upgrade recommendation bridge)
- Skill templates: `prompt-dsl-system/05_skill_registry/templates/skill_template/`
  - Files: `skill.yaml.template`, `references/README.template`, `scripts/README.template`, `assets/README.template`
- Deprecated skills status:
  - archived files under `prompt-dsl-system/05_skill_registry/deprecated/skills/**`
  - current archived count: `28`

## 2) Current Pipelines Baseline

- Pipeline files (`pipeline_*.md`) count: `13`
- `pipeline_sql_oracle_to_dm8.md`: `4` steps, all reference `skill_hongzhi_universal_ops`
- `pipeline_ownercommittee_audit_fix.md`: `5` steps, all reference `skill_hongzhi_universal_ops`
- `pipeline_bpmn_state_audit_testgen.md`: `5` steps, all reference `skill_hongzhi_universal_ops`
- `pipeline_db_delivery_batch_and_runbook.md`: `3` steps, all reference `skill_hongzhi_universal_ops`
- `pipeline_bugfix_min_scope_with_tree.md`: `4` steps, all reference `skill_hongzhi_universal_ops`
- `pipeline_skill_creator.md`: `5` steps, all reference `skill_hongzhi_universal_ops` (modes: governance/meta/meta/meta/docs)
- `pipeline_project_bootstrap.md`: `5` steps, all reference `skill_hongzhi_universal_ops` — batch skill generation + profile input
- `pipeline_skill_promote.md`: `3` steps, all reference `skill_hongzhi_universal_ops` — staging→deployed promotion + mandatory ledger
- `pipeline_module_migration.md`: `7` steps (Step0–Step5 + acceptance), all reference `skill_hongzhi_universal_ops` — single-module migration assembly line + materialize_skills switch + Step0 auto-discovery
- `pipeline_plugin_discover.md`: `3` steps (status → decide → discover hard gate), references `skill_governance_plugin_status` + `skill_governance_plugin_runner`
- `pipeline_project_stack_bootstrap.md`: `4` steps, all reference `skill_hongzhi_universal_ops` — project stack KB bootstrap (declared/discovered + evidence + closure)
- `pipeline_requirement_to_prototype.md`: `4` steps, all reference `skill_hongzhi_universal_ops` — PM链路（需求澄清→流程切片→原型）
- `pipeline_kit_self_upgrade.md`: `4` steps, references `skill_governance_audit_kit_quality` + `skill_hongzhi_universal_ops` — kit 主线升级前质量评分与改造闭环

## 3) Current Tools Boundary

- `run.sh`: stable wrapper (`/usr/bin/python3`) for `pipeline_runner.py`; supports `HONGZHI_VALIDATE_STRICT=1` env var for anti-false-green; includes `selfcheck` and `self-upgrade` unified entries; supports strict self-upgrade preflight (`--strict-self-upgrade` or `HONGZHI_SELF_UPGRADE_STRICT=1`) with quality + dimension contract gate (`HONGZHI_SELFCHECK_MIN_SCORE` / `HONGZHI_SELFCHECK_MIN_LEVEL` / `HONGZHI_SELFCHECK_MAX_LOW_DIMS` / `HONGZHI_SELFCHECK_REQUIRED_DIMS`)
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
- `golden_path_regression.sh`: end-to-end regression (132 checks: Phase1-8 core + Phase9-14 discovery + Phase15-19 plugin runner/governance + Phase20-22 capability registry/smart reuse/no-state-write + Phase23 packaging/contract v4 + uninstalled install-hint check + Phase24 release build/version triplet/gitignore/governance no-write guard + Phase25 token TTL/scope/symlink/limits/capability-index-gating/pipeline-decision chain + Phase26 calibration low-confidence/strict-exit21/workspace artifacts/capability fields + Phase27 hint loop/layout adapters/reuse validation/governance zero-write/index hint metrics + Phase28 profile_delta hint assetization/verification/scope gating/index gating + Phase29 federated index write/query/explain/scope gating/zero-write governance + Phase30 zero-touch/status-index, full snapshot guard, policy parse fail-closed, machine-path safety, jsonl concurrency, IO stats stability, composed endpoint extraction, hint effectiveness + Phase31 unified scan graph/cross-command reuse/mismatch gate + Phase32 schema/versioned scan-graph + mismatch reason + machine-line json + default hot-reuse/no-rescan + governance zero-write + full snapshot/limits decoupling guard + Phase33 machine-json roundtrip/no-newline + deterministic artifacts/candidates ordering + mismatch enum/suggestion + read-command zero-touch probe guard + Phase34 contract schema v1/v2 + validator + additive guard + Phase35 company scope gate + governance skill lifecycle convergence + Phase36 strict self-upgrade preflight + contract sample replay + A3 template baseline + Phase37 validate default post-gates + Phase38 health_report post-gate section + Phase39 runbook post-gate fail-first + Phase40 selfcheck quality threshold gate + Phase41 selfcheck dimension contract gate)
- `module_profile_scanner.py`: generates discovered profile (Layer2) — scanning + grep + fingerprint + multi-root + concurrent + incremental + `--out-root`/`--read-only`/`--workspace-root`
- `module_roots_discover.py`: auto-discovers module roots from identity hints + structure fallback + optional `--module-key` (auto-discover) + `--out-root`/`--read-only` (Layer2R)
- `structure_discover.py` v2: auto-identifies module structure — endpoint v2, per-file incremental cache, `--out-root`/`--read-only`/`--workspace-root` (Layer2S)
- `cross_project_structure_diff.py` v2: compares endpoint signatures, reports added/removed/changed, `--read-only`
- `auto_module_discover.py`: discovers module candidates without `--module-key` — package prefix clustering, scoring, top-k, `--read-only`
- `project_stack_scanner.py`: scans target repository and outputs `project_stacks/<project_key>/stack_profile.discovered.yaml` with machine-verifiable evidence list
- `kit_selfcheck.py`: outputs toolkit quality scorecards (`kit_selfcheck_report.json` + `.md`) across 7 dimensions with missing-path recommendations
  - machine signal: `KIT_CAPS <abs_json_path> path="..." json='...'`
- `kit_selfcheck_gate.py`: enforces strict self-upgrade quality + dimension contract from selfcheck report (`overall_score`, `overall_level`, `low_dimensions`, `required_dimensions`, `summary.dimension_count`)
- `contract_schema_v1.json` / `contract_schema_v2.json`: machine-line contracts; v2 is additive over v1
- `contract_validator.py`: validates machine lines; default schema auto-select prefers v2, with optional `--baseline-schema` additive guard
- `contract_samples/`: replayable validator sample logs and replay script (`replay_contract_samples.sh`)
- `tools/artifacts/templates/kit_self_upgrade/`: A3 closure templates (`change_ledger`, `rollback_plan`, `cleanup_report`)
- `kit_self_upgrade_template_guard.py`: validates A3 template existence + required sections/placeholders
- `health_post_validate_sync.py`: syncs validate post-gate summary into `health_report` JSON/Markdown section
- `hongzhi_plugin.py`: v4 contract-capable runner — discover/diff/profile/migrate/status/clean, snapshot-diff read-only contract, governance (enabled/deny/allow/token), smart incremental, capability registry, `HONGZHI_CAPS` line, capabilities.jsonl journal
- `calibration_engine.py`: lightweight calibration layer for discover confidence, reasons enum, and workspace-only hint/report artifacts
- `layout_adapters.py`: layout adapters v1 for multi-module/non-standard Java root detection and roots mapping
- `scan_graph.py`: Unified Scan Graph v1 (single walk file index + java/template hints + cache key + io stats)
- `hongzhi_ai_kit/hint_bundle.py`: profile_delta hint bundle schema/build/verify helpers (path + inline JSON)
- `hongzhi_ai_kit/federated_store.py`: federated index persistence/query helpers (atomic write + bounded runs + ranking)
- `hongzhi_ai_kit`: installable python package wrapper with module/console entry support
- `pyproject.toml` (repo root): packaging metadata + console_scripts (`hongzhi-ai-kit`, `hzkit`, `hz`)
- `PLUGIN_RUNNER.md`: plugin runner documentation (install, governance, v3/v4 contract, workspace/global state)

## 4) Conventions Documents

- `HONGZHI_COMPANY_CONSTITUTION.md`: 34 rules, company-domain governance
- `SKILL_SPEC.md`: YAML schema, registry contract, trace parameters, template generation, bundled resources, progressive disclosure + NavIndex, skill status lifecycle (staging/deployed/deprecated)
- `COMPLIANCE_MATRIX.md`: 15 requirements mapped to implementation
- `ROLLBACK_INSTRUCTIONS.md`: rollback procedure
- `FACT_BASELINE.md`: this document
- `CPP_STYLE_NAMING.md`: C++ style naming conventions for Java8+SpringBoot
- `PERSONAL_DEV_STANDARD.md`: personal C++-aligned dev standard (team constraints first, naming hard rules, self-monitor loop handling)
- `KIT_QUALITY_MODEL.md`: kit quality dimensions and scoring bands for self-upgrade gating
- `CONTRACT_COMPATIBILITY_STRATEGY.md`: machine contract versioning and additive compatibility rules
- `SQL_COMPAT_STRATEGY.md`: SQL dual-stack delivery specification
- `PROJECT_PROFILE_SPEC.md`: project profile input contract for pipeline_project_bootstrap
- `PROJECT_TECH_STACK_SPEC.md`: per-project stack KB spec (declared/discovered + evidence + merge policy)
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

## 10) Release Build + Version Triplet (R18)

- Version semantics are separated and emitted together:
  - `package_version`
  - `plugin_version`
  - `contract_version`
- `status` now emits machine-readable:
  - `HONGZHI_STATUS package_version=... plugin_version=... contract_version=... enabled=...`
- `discover` capability pointer now emits machine-readable:
  - `HONGZHI_CAPS <abs_path> package_version=... plugin_version=... contract_version=...`
- Governance block output carries version triplet and remains zero-write:
  - `HONGZHI_GOV_BLOCK code=... ... package_version=... plugin_version=... contract_version=...`
- Release build smoke is gated in regression:
  - wheel install smoke
  - sdist build smoke

## 11) Governance v3 + Limits + Pipeline Decision Gate (R19)

- Capability index entry schema upgraded (v1 fields on per-project entry):
  - `repo_fingerprint`
  - `created_at`
  - `latest`
  - `runs[]`
  - `versions{package,plugin,contract}`
  - `governance{enabled,token_used,policy_hash}`
- Capabilities outputs enriched:
  - `layout`, `module_candidates`, `ambiguity_ratio`
  - `limits_hit`, `limits{max_files,max_seconds,...}`
  - `scan_stats{files_scanned,cache_hit_files,...}`
- Governance permit token supports TTL/scope JSON token format; invalid/expired/scope-mismatch token is rejected.
- Allow/deny policy matching is realpath/symlink hardened.
- Limits behavior:
  - normal mode: warn + `limits_hit=true` + exit `0`
  - strict mode: exit `20`
- New governance-only status skill exists:
  - `skill_governance_plugin_status`
- Plugin discover pipeline upgraded to `status -> decide -> discover` hard-gate flow.

## 12) Calibration Layer & Strict Hint Gate (R20)

- Discover now produces workspace-only calibration artifacts:
  - `calibration/calibration_report.json`
  - `calibration/calibration_report.md`
  - `calibration/hints_suggested.yaml` (default enabled)
- Capabilities payloads (`capabilities.json` and `capabilities.jsonl`) now include:
  - `calibration.needs_human_hint`
  - `calibration.confidence`
  - `calibration.confidence_tier`
  - `calibration.reasons[]`
  - `calibration.suggested_hints_path` / `calibration.report_path`
- Strict mode gating:
  - if `needs_human_hint=true`, discover exits `21` and emits `exit_hint=needs_human_hint` in summary.
  - non-strict mode keeps `exit=0` with warning markers.
- Read-only and governance guarantees remain unchanged:
  - target `repo_root` stays no-write by default.
  - governance block paths (`10/11/12`) still produce zero workspace/state writes.

## 13) Hint Loop & Layout Adapters (R21)

- Discover hint loop:
  - strict `exit=21` with `needs_human_hint=1` now emits workspace hint bundle (`discover/hints.json`) and stdout `HONGZHI_HINTS <abs_path>`.
  - rerun supports `--apply-hints <path>` + `--hint-strategy conservative|aggressive`.
- Capabilities contract fields (additive, backward compatible):
  - `hints{emitted,applied,bundle_path,source_path,strategy}`
  - `layout_details{adapter_used,candidates_scanned,...}`
  - `smart.reuse_validated`
  - `limits_suggestion`
- Layout adapters v1:
  - supports Maven multi-module and non-standard Java roots (`java/`, `app/src/main/java`, `backend/src/main/java`).
- Prompt-DSL loop closure:
  - new skill `skill_governance_plugin_discover_with_hints`
  - discover pipeline now documents status -> decide -> discover and conditional hint rerun policy (`enable_hint_loop`).

## 14) Hint Assetization (R22)

- Discover strict ambiguity path now assetizes hints as `profile_delta` bundle and emits `HONGZHI_HINTS`.
- Apply-hints input supports:
  - bundle file path
  - inline JSON string
- Apply verification now checks:
  - expiry (`expires_at`/`ttl_seconds`) -> strict exit `22`
  - scope (`discover`/`*`)
  - fingerprint match (unless `--allow-cross-repo-hints`)
- Hint emission scope gate:
  - when permit-token scope misses `hint_bundle`, strict returns `23`
  - machine line: `HONGZHI_HINTS_BLOCK ...`
- Capabilities outputs now include additive `hint_bundle{kind,path,verified,expired,ttl_seconds,created_at,expires_at}`.

## 15) Capability Index Federation (R23)

- Global federated index files (governance-allowed path only):
  - `<global_state_root>/federated_index.json`
  - `<global_state_root>/federated_index.jsonl` (optional)
  - `<global_state_root>/repos/<fp>/index.json` (optional mirror)
- Federated writes are policy + token-scope gated independently:
  - missing `federated_index` scope with token:
    - strict: exit `24` + `HONGZHI_INDEX_BLOCK ...`
    - non-strict: warn, no federated write
- New CLI subcommands:
  - `index list`
  - `index query`
  - `index explain`
- Discover emits `HONGZHI_INDEX <abs_path>` when federated index update is committed.

## 16) Plugin v4+ Hardening (R24)

- Path resolution hardening:
  - `status` / `index` use read-only root resolution (`resolve_*_root(read_only=True)`), no `.write_test` probing files.
  - machine lines now include parse-safe path fields (`path="<abs_path>"`) for `HONGZHI_CAPS/HONGZHI_HINTS/HONGZHI_INDEX`.
- Read-only contract hardening:
  - snapshot-diff guard now always uses full before/after snapshots (not truncated by `--max-files` / `--max-seconds`).
- Governance fail-closed:
  - `policy.yaml` parse error returns exit `13` with `HONGZHI_GOV_BLOCK reason=policy_parse_error`.
- Concurrency hardening:
  - `capability_store` and `federated_store` atomic JSON writes now use unique temp files + fsync.
  - `atomic_append_jsonl` uses locked append (`flock` fallback lockfile) to avoid dropped lines under parallel runs.

## 17) Contract Schema v1 + Validator Hard Gate (R28)

- Added schema file:
  - `prompt-dsl-system/tools/contract_schema_v1.json`
  - defines machine line types, required fields, json payload required keys, enums, exit code map, additive policy.
- Added zero-dependency validator:
  - `prompt-dsl-system/tools/contract_validator.py`
  - validates stdout logs from `--stdin` or `--file`.
  - output: `CONTRACT_OK=1` (exit 0) or `CONTRACT_OK=0 ...` (exit 2).
- Golden regression hard gate:
  - Phase34 validates schema JSON, validator CLI, discover/gov-block/exit25 stdout contract compliance, and additive schema guard.
- Discover observability additions:
  - `scan_io_stats` (`layout_adapter_runs`, `java_files_scanned`, `templates_scanned`, `snapshot_files_count`, cache stats).
  - `hint_effective` + `confidence_delta` emitted in summary and capabilities (`hints` payload).
- Endpoint extraction hardening:
  - `structure_discover.py` gains composed-annotation/symbolic path fallback; symbolic signals persisted in structure output.

## 17) Unified Scan Graph & Cross-Command Reuse (R25)

- Added `scan_graph.py` as a reusable scan middle layer:
  - output: workspace `scan_graph.json`
  - cache: workspace `scan_cache/<cache_key>.json`
  - payload: `file_index`, `java_hints`, `template_hints`, `io_stats`, `cache_key`
- Discover now consumes scan graph and publishes additive contract fields:
  - `scan_graph{used,cache_key,cache_hit_rate,java_files_indexed,bytes_read,io_stats}`
  - summary adds `scan_graph_used`, `scan_cache_hit_rate`, `java_files_indexed`, `bytes_read`
- Profile/diff support scan graph reuse:
  - `profile --scan-graph <path>`
  - `diff --old-scan-graph <path> --new-scan-graph <path>`
- Strict consistency guard:
  - scan graph spot-check mismatch in strict mode exits `25` (`exit_hint=scan_graph_mismatch`)

## 18) Additive Contract & Scan Graph Explainability (R26)

- Scan graph contract is versioned and auditable:
  - `schema_version` (v1.1 additive field)
  - `producer_versions` (`package_version`, `plugin_version`, `contract_version`)
  - `graph_fingerprint` (stable fingerprint on roots + indexed file metadata)
- Strict mismatch (`exit=25`) now provides machine-readable explainability:
  - summary fields: `mismatch_reason`, `mismatch_detail`
  - `HONGZHI_CAPS` / `HONGZHI_INDEX` additive fields include same mismatch markers
  - mismatch reasons enum includes:
    - `schema_version_mismatch`
    - `fingerprint_mismatch`
    - `producer_version_mismatch`
    - `cache_corrupt`
    - `unknown`
- Machine line additive JSON payload:
  - `HONGZHI_CAPS` / `HONGZHI_INDEX` / `HONGZHI_HINTS` append `json='{"path":...}'`
  - payload includes `path`, `command`, `versions`, `repo_fingerprint`, `run_id`
  - rollback switch: `HONGZHI_MACHINE_JSON_ENABLE=0` (legacy-only output fallback)
- Cross-command default reuse strengthened:
  - `profile`/`diff` can auto-locate latest discover scan graph even if latest pointer was updated by non-discover run.
  - hot reuse emits command-local no-rescan counters (`java_files_indexed=0`, `bytes_read=0`) while preserving source stats additively.

## 19) Machine JSON Roundtrip & Deterministic Output (R27)

- Machine-line additive JSON payload contract is now roundtrip-safe:
  - single-line payload
  - direct `json.loads(...)` parse success
  - backward-compatible legacy machine fields retained
- Machine JSON control:
  - CLI: `--machine-json 0|1` (default `1`)
  - env override (higher priority): `HONGZHI_MACHINE_JSON_ENABLE`
- Unified machine JSON encoding is applied to all machine lines:
  - `HONGZHI_CAPS`, `HONGZHI_INDEX`, `HONGZHI_HINTS`
  - `HONGZHI_STATUS`, `HONGZHI_GOV_BLOCK`
  - `HONGZHI_INDEX_BLOCK`, `HONGZHI_HINTS_BLOCK`
- Discover output determinism hardening:
  - `capabilities.artifacts[]` stable sorted output (relpath-based)
  - `capabilities.roots[]` stable sorted output (`module_key + category + path`)
  - `metrics.candidates[]` stable sorted output (`score desc`, tie-breakers by identity fields)
- Strict mismatch (`exit=25`) now includes:
  - `mismatch_reason` (enum-constrained)
  - `mismatch_detail`
  - `mismatch_suggestion` (short remediation guidance)

## 20) Company Scope Gate & Skills Lifecycle Convergence (R29)

- Governance plugin skills lifecycle converged to deployed state:
  - `skill_governance_plugin_discover`
  - `skill_governance_plugin_runner`
  - `skill_governance_plugin_status`
  - `skill_governance_plugin_discover_with_hints`
- Added additive company scope signal across machine outputs:
  - summary includes `company_scope=...`
  - machine lines include `company_scope=\"...\"`
  - machine JSON payload includes `company_scope`
- Added optional hard gate (default off):
  - enable by env `HONGZHI_REQUIRE_COMPANY_SCOPE=1`
  - scope source precedence: env `HONGZHI_COMPANY_SCOPE` > CLI `--company-scope` > default `hongzhi-work-dev`
  - mismatch blocks with `HONGZHI_GOV_BLOCK reason=company_scope_mismatch` and exit `26`
- Regression hardening:
  - Phase35 validates lifecycle convergence, company scope machine fields, mismatch block semantics, and mismatch-path zero-write.

## 21) Kit Strict Self-Upgrade + Contract v2 Compatibility (R39/R40)

- `run.sh` strict self-upgrade preflight chain is available:
  - `selfcheck -> contract_validator -> selfcheck_gate -> pipeline_contract_lint -> skill_template_audit -> validate(strict)`
  - trigger: `--strict-self-upgrade` or `HONGZHI_SELF_UPGRADE_STRICT=1`
  - any preflight gate failure is fail-fast.
- Contract schema evolution baseline:
  - `contract_schema_v2.json` is added as current schema.
  - `contract_schema_v1.json` remains baseline compatibility anchor.
- Validator behavior:
  - default schema auto-detection prefers v2, falls back to v1.
  - strict preflight runs validator with additive baseline guard (`--baseline-schema v1`) when v2 is available.
- Compatibility governance:
  - strategy document: `CONTRACT_COMPATIBILITY_STRATEGY.md`.
  - policy: schema upgrades are additive-only unless explicit migration approval exists.

## 22) Self-Upgrade Templates & Contract Replay Baseline (R41)

- Closure templates are standardized for kit self-upgrade:
  - `tools/artifacts/templates/kit_self_upgrade/A3_change_ledger.template.md`
  - `tools/artifacts/templates/kit_self_upgrade/A3_rollback_plan.template.md`
  - `tools/artifacts/templates/kit_self_upgrade/A3_cleanup_report.template.md`
- Machine contract replay baseline is available:
  - `tools/contract_samples/sample_*.log`
  - `tools/contract_samples/replay_contract_samples.sh`
- Regression hardening:
  - Phase36 validates strict self-upgrade preflight in isolated temp repo.
  - Phase36 validates contract sample replay.
  - Phase36 validates A3 template baseline presence.

## 23) Validate Default Post-Gates (R42)

- `run.sh validate` now runs post-gates after core validate/audit/lint:
  1. `contract_samples/replay_contract_samples.sh`
  2. `kit_self_upgrade_template_guard.py`
- Default behavior:
  - both post-gates are default-on.
  - any failure marks validate as failed.
- Regression hardening:
  - Phase37 validates post-gate execution signals in validate stdout:
    - `[contract_replay] PASS`
    - `[template_guard] PASS`

## 24) Health Report Post-Gate Section (R43)

- Validate chain now writes a dedicated `post_validate_gates` section into:
  - `health_report.json`
  - `health_report.md`
- Section fields include:
  - `overall_status`
  - `gates[]` (`name`, `status`, `exit_code`)
- Required gate visibility:
  - `contract_sample_replay`
  - `kit_template_guard`
- Regression hardening:
  - Phase38 validates health report JSON section and markdown section markers.

## 25) Strict Selfcheck Quality Threshold Gate (R44)

- Strict preflight now enforces quality thresholds from selfcheck report before lint/audit/validate.
- Default thresholds:
  - `overall_score >= 0.85`
  - `overall_level >= high`
  - `low_dimensions <= 0`
- Threshold knobs (env):
  - `HONGZHI_SELFCHECK_MIN_SCORE`
  - `HONGZHI_SELFCHECK_MIN_LEVEL`
  - `HONGZHI_SELFCHECK_MAX_LOW_DIMS`
- Regression hardening:
  - Phase40 validates low-quality report is blocked.
  - Phase40 validates high-quality report is accepted.

## 26) Strict Selfcheck Dimension Contract Gate (R45)

- Strict preflight now validates selfcheck dimension contract:
  - required dimensions set must be complete
  - `summary.dimension_count` must equal actual dimensions size
- Default required dimensions:
  - `generality`, `completeness`, `robustness`, `efficiency`, `extensibility`, `security_governance`, `kit_mainline_focus`
- Dimension contract knob (env):
  - `HONGZHI_SELFCHECK_REQUIRED_DIMS` (comma-separated override)
- Regression hardening:
  - Phase41 validates missing required dimensions are blocked.
  - Phase41 validates summary dimension count mismatch is blocked.
