# Kit Quality Model

Purpose: define measurable quality dimensions for `beyond-dev-ai-kit` self-upgrade tasks.

Scope: toolkit repository only (`prompt-dsl-system/**` and package/docs tooling).

## Dimensions

1. `generality`
- Can the kit adapt to multiple projects/modules without hard-coded assumptions?
- Signals: project/module profile specs, migration/bootstrapping pipelines, stack profile contracts.

2. `completeness`
- Are prompt/DSL/skill/pipeline/tool/document chains complete enough for delivery?
- Signals: active skills registry, pipeline coverage, baseline/compliance docs.

3. `robustness`
- Does the kit have operational gates and rollback-safe flows?
- Signals: validate/audit/lint/guard/regression scripts, constitution rules.

4. `efficiency`
- Does the kit avoid redundant scans and unnecessary cost?
- Signals: scan graph, smart reuse tools, bounded scanning controls.

5. `extensibility`
- Can new skills/pipelines be added with low risk and low friction?
- Signals: skill template, skill creator/promote pipelines, project bootstrap pipeline.

6. `security_governance`
- Does the kit enforce safety, scope, read-only defaults, and governance blocks?
- Signals: constitution, plugin governance gates, path guard rules, policy fail-closed behavior.

7. `kit_mainline_focus`
- Does current work stay on toolkit mainline and avoid external repo mutation?
- Signals: Rule 24 enforcement and kit-only change scope.

## Scoring

- Per-dimension score range: `0.0 ~ 1.0`.
- Suggested bands:
  - `high`: `>= 0.85`
  - `medium`: `>= 0.65`
  - `low`: `< 0.65`
- Overall score is arithmetic mean of dimension scores.

## Minimum gate for upgrade acceptance

- No dimension should be `low` for release-grade self-upgrade runs.
- If any dimension is `low`, upgrade run must include mitigation actions in change ledger.
- Strict self-upgrade enforcement is implemented by `prompt-dsl-system/tools/kit_selfcheck_gate.py` and wired in `run.sh --strict-self-upgrade`.
- Default strict thresholds:
  - `overall_score >= 0.85`
  - `overall_level >= high`
  - `low_dimensions <= 0`
- Default strict dimension contract:
  - required dimensions: `generality`, `completeness`, `robustness`, `efficiency`, `extensibility`, `security_governance`, `kit_mainline_focus`
  - `summary.dimension_count` equals actual `dimensions` size
