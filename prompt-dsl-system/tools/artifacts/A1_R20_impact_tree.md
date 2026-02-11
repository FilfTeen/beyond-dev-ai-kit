# A1_R20_impact_tree

## Scope
- Repo: `prompt-dsl-system/**` only.
- Goal: add calibration explainability layer for discover without breaking read-only/governance guarantees.

## Change Tree
- Discover execution path (`prompt-dsl-system/tools/hongzhi_plugin.py`)
  - Add calibration invocation after discover scan stage.
  - Add strict gate `exit=21` when `needs_human_hint=true`.
  - Keep `HONGZHI_CAPS` + summary line contract; extend summary fields.
  - Keep governance blocked runs zero-write (unchanged main gate).
- Contract payload (`capabilities.json` + `capabilities.jsonl`)
  - Add `calibration` object (needs_human_hint/confidence/tier/reasons/hint/report paths).
  - Add jsonl calibration summary fields for downstream agent replay.
- New calibration module (`prompt-dsl-system/tools/calibration_engine.py`)
  - Compute confidence/reasons/suggested_hints using discover metrics and structure signals.
  - Emit workspace artifacts under `calibration/` only.
- Regression (`prompt-dsl-system/tools/golden_path_regression.sh`)
  - Add Phase26 (4 checks) for strict/non-strict behavior and artifact/schema assertions.
- Fixtures (`prompt-dsl-system/tools/_tmp_structure_cases/...`)
  - Add endpoint-miss case and two-module ambiguity case for deterministic low-confidence behavior.
- Documentation/baselines
  - Update `PLUGIN_RUNNER.md`, `FACT_BASELINE.md`, `COMPLIANCE_MATRIX.md` with R20 semantics.

## Risk Surface
- Behavioral change: strict discover ambiguity handling moves from legacy early exit to calibration-based `exit=21`.
- Contract change: additive only; existing fields retained.
- Governance/read-only: unchanged gate ordering; verified by full regression pass.
