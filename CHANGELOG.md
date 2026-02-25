# Changelog

All notable changes to **beyond-dev-ai-kit** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [1.3.0] — 2026-02-25

### Added

- Runtime output tracking guard: `runtime_outputs_tracking_guard.py`
- Double-run consistency guard: `double_run_consistency_guard.py`
- History archive index under `prompt-dsl-system/tools/history/**`
- Deprecated registry archive index: `prompt-dsl-system/05_skill_registry/deprecated/README.md`

### Changed

- Runtime outputs are now untracked by default (gitignored + removed from git index)
- `run.sh validate` post-gates now include runtime outputs tracking guard
- `Makefile release-check` now includes runtime outputs guard and double-run consistency guard
- CI guardrail workflow adds runtime outputs guard and double-run consistency check
- Historical tool docs moved from `prompt-dsl-system/tools` root to `prompt-dsl-system/tools/history/{changelog,test-notes}`
- Static historical run plans moved to `prompt-dsl-system/tools/history/run-plans/`
- Artifact retention reduced to latest 3 rounds (`R27-R29`) plus current non-round artifacts
- Package and contract version bumped to `1.3.0`

## [1.2.0] — 2026-02-25

### Added

- Agent auto-injection: `.cursorrules`, `.github/copilot-instructions.md`, `.windsurfrules`
- 5 new skills: `skill_test_gen`, `skill_security_audit`, `skill_api_design_review`, `skill_performance_analysis`, `skill_docs_i18n`
- 2 new pipelines: `pipeline_test_gen.md`, `pipeline_security_audit.md`
- Skill registry expanded from 12 to 17; pipeline count from 13 to 15

### Changed

- `company_profile.yaml`: formal company name with business context
- Contract version bumped to 1.2.0
- Plugin version bumped to 1.2.0

## [1.1.0] — 2026-02-13

### Added

- Contract schema v2 with additive compatibility guard
- Baseline provenance attestation gate (`baseline_provenance_guard.py`)
- Pipeline trust full-coverage gate (`pipeline_trust_coverage_guard.py`)
- Gate mutation resilience guard (`gate_mutation_guard.py`)
- Performance budget gate with trend analysis (`performance_budget_guard.py`)
- CI workflow (`kit_guardrails.yml`) with dual-approval for baseline changes
- Company scope gate with optional hard enforcement (exit 26)
- Federated index for cross-project run discovery
- Scan graph caching and smart reuse
- Hint bundle system for profile-delta human hints
- HMAC signing mode for baselines (optional)
- Constitution Rule 16–50 governance framework
- 6 business-domain skills (code/sql/frontend/process/release/docs)
- `QUICKSTART.md`, `EXIT_CODES.md`, `AGENTS_ADAPTER.md`
- Architecture diagram in README
- Modularized `pipeline_yaml_parser.py`, `pipeline_profile_injector.py`, `hongzhi_ai_kit/snapshot.py`
- `baseline_rebuild_all.sh` — atomic baseline rebuild script
- MIT LICENSE file

### Changed

- Plugin version to 1.1.0
- Contract version to 1.1.0
- Summary version to 3.0
- `pipeline_runner.py` reduced by 488 lines via module extraction
- `hongzhi_plugin.py` reduced by 55 lines via snapshot extraction
- Constitution rules annotated with severity levels (CRITICAL/HIGH/MEDIUM)

### Fixed

- Phase40 selfcheck gate fixture missing `agent_active_ops` dimension
- Baseline rebuild order causing hash drift (trust→provenance→manifest)
- FACT_BASELINE.md section numbering duplicate
- Empty skill subdirectories (added `.gitkeep`)

## [1.0.0] — 2025-12-01

### Added

- Initial release of prompt-dsl-system
- `hongzhi_plugin.py` v1.0.0 runner with governance
- `pipeline_runner.py` with YAML DSL pipeline execution
- 13 pipelines (discover, scan, migration, etc.)
- Skill registry with template system
- Contract schema v1
- `kit_selfcheck.py` quality scorecard
- Constitution Rule 01–15
