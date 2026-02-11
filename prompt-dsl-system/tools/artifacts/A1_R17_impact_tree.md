# A1 R17 Impact Tree

## Scope

- Packaging and entrypoints:
  - `pyproject.toml`
  - `prompt-dsl-system/tools/hongzhi_ai_kit/cli.py`
  - `prompt-dsl-system/tools/hongzhi_ai_kit/__init__.py`
- Runner contract and governance output:
  - `prompt-dsl-system/tools/hongzhi_plugin.py`
- Skill/pipeline integration:
  - `prompt-dsl-system/05_skill_registry/skills/governance/skill_governance_plugin_runner.yaml`
  - `prompt-dsl-system/05_skill_registry/skills.json`
  - `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_plugin_discover.md`
- Regression:
  - `prompt-dsl-system/tools/golden_path_regression.sh` (Phase23)
- Docs/baselines:
  - `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
  - `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
  - `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`

## Impact Graph

- R17 Goal: installable + universal CLI + machine-readable contract
  - A. Packaging layer
    - editable install (`pip install -e .`)
    - module entry (`python3 -m hongzhi_ai_kit`)
    - console entry (`hongzhi-ai-kit`)
  - B. Runtime contract v4
    - `HONGZHI_CAPS <abs_path>` stdout line
    - append-only `capabilities.jsonl` workspace journal
    - governance block line (`HONGZHI_GOV_BLOCK ...`) without state writes
  - C. Agent workflow layer
    - governance plugin runner skill
    - plugin discover pipeline (status -> discover -> capability reading)
  - D. Validation layer
    - Phase23 package/module/entry/contract checks

## Risk & Mitigation

- Risk: packaging path mismatch for hyphenated `prompt-dsl-system`
  - Mitigation: setuptools `package-dir` + `py-modules` explicit mapping
- Risk: governance blocked path accidentally writes artifacts
  - Mitigation: early governance gate + regression `governance_disabled_no_outputs`
- Risk: contract change breaks v3 parsers
  - Mitigation: keep v3 `hongzhi_ai_kit_summary` and only append v4 lines/fields
