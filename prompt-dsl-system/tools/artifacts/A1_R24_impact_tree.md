# A1_R24_impact_tree

## Scope
- `prompt-dsl-system/tools/hongzhi_plugin.py`
- `prompt-dsl-system/tools/hongzhi_ai_kit/paths.py`
- `prompt-dsl-system/tools/hongzhi_ai_kit/capability_store.py`
- `prompt-dsl-system/tools/hongzhi_ai_kit/federated_store.py`
- `prompt-dsl-system/tools/structure_discover.py`
- `prompt-dsl-system/tools/golden_path_regression.sh`
- `prompt-dsl-system/tools/_tmp_structure_cases/case8_composed_annotation/*`
- docs: `PLUGIN_RUNNER.md`, `FACT_BASELINE.md`, `COMPLIANCE_MATRIX.md`

## Impact Tree
1. Runtime hardening
- Status/index root resolution switched to zero-touch read-only mode.
- Read-only guard snapshot before/after no longer depends on `--max-files`.
- Governance policy parse is fail-closed with exit `13` + `HONGZHI_GOV_BLOCK reason=policy_parse_error`.

2. Contract/observability additive fields
- Machine lines now include parse-safe `path="..."` for `HONGZHI_CAPS/HONGZHI_HINTS/HONGZHI_INDEX`.
- Discover summary adds `hint_effective` and `confidence_delta`.
- Capabilities add `scan_io_stats` and hints effectiveness fields.

3. Concurrency safety
- Atomic JSON writes now use unique tmp files + fsync (capability/federated stores).
- JSONL append now uses locked append (`flock`, lockfile fallback).

4. Accuracy and IO
- Discover removes duplicate layout adapter full scan pass.
- Added composed/symbolic endpoint extraction fallback in `structure_discover.py`.

5. Regression enforcement
- Added Phase30 (8 checks), total regression checks increased to 86.
