# A1 R16 Impact Tree

## Scope

- Plugin runner: `prompt-dsl-system/tools/hongzhi_plugin.py`
- Installable package helpers:
  - `prompt-dsl-system/tools/hongzhi_ai_kit/paths.py`
  - `prompt-dsl-system/tools/hongzhi_ai_kit/capability_store.py`
- Regression: `prompt-dsl-system/tools/golden_path_regression.sh`
- Governance/docs baselines:
  - `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
  - `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
  - `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`
  - `prompt-dsl-system/00_conventions/HONGZHI_COMPANY_CONSTITUTION.md`

## Dependency Tree

- Root capability: Agent-native plugin contract v3
  - Branch A: Capability Registry (global state)
    - Path root resolver (`resolve_global_state_root`)
    - Atomic index write (`capability_index.json`)
    - Latest pointer (`<fp>/latest.json`)
    - Run metadata (`<fp>/runs/<run_id>/run_meta.json`)
  - Branch B: Smart Incremental (`--smart`)
    - Reuse gating: age, fp/vcs, artifact existence, cache ratio
    - Reuse materialization: link/copy command artifacts into new workspace
    - Summary contract: `smart_reused`, `reused_from`
  - Branch C: Governance integrity
    - Disabled/deny/allow/token state machine unchanged
    - Governance blocked path does not write global state
    - Read-only snapshot-diff guard remains active
  - Branch D: Regression coverage
    - Phase20 capability index smoke
    - Phase21 smart reuse smoke
    - Phase22 disabled-state no-write

## Risk Nodes

- Smart false-positive reuse
  - Mitigation: strict defaults (`age=600`, `cache>=0.90`, `drift=strict`)
- Global state corruption
  - Mitigation: atomic JSON writes with temp + rename
- Repo write regression
  - Mitigation: snapshot-diff guard unchanged and covered by regression
