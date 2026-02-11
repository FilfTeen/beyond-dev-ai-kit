# A1_R23_impact_tree

## Goal
Round23 adds **Capability Index Federation** so agent/runtime can query cross-run, cross-project discoverability without touching target repos.

## Impact Tree
- Runtime core
  - `prompt-dsl-system/tools/hongzhi_plugin.py`
    - Added federated index write hook for discover/diff/profile/migrate
    - Added machine lines:
      - `HONGZHI_INDEX ...` on federated update
      - `HONGZHI_INDEX_BLOCK ...` on scope block
    - Added strict exit code `24` for federated scope missing under strict mode
    - Added `index` subcommands:
      - `index list`
      - `index query`
      - `index explain`
    - Preserved governance hard gate (`10/11/12`) zero-write behavior
- Package helpers
  - `prompt-dsl-system/tools/hongzhi_ai_kit/federated_store.py` (new)
    - atomic JSON persistence (`federated_index.json`)
    - atomic jsonl append (`federated_index.jsonl`)
    - bounded per-repo runs[]
    - ranking query logic (endpoint > keyword > recency > ambiguity > confidence tier)
- Regression gate
  - `prompt-dsl-system/tools/golden_path_regression.sh`
    - Added Phase29 (8 checks)
- Docs/baseline
  - `PLUGIN_RUNNER.md`, `FACT_BASELINE.md`, `COMPLIANCE_MATRIX.md`

## Risk Notes
- Backward compatibility preserved:
  - existing `HONGZHI_CAPS`, `HONGZHI_STATUS`, `HONGZHI_GOV_BLOCK`, summary line kept
  - v4 fields retained; federated fields are additive
- Governance deny paths remain pre-dispatch hard gate; deny path still writes nothing.
