# A1_R25 Impact Tree

## Scope
- Introduce Unified Scan Graph v1 (`scan_graph.py`) as shared scan middle layer.
- Reuse scan graph across `discover`, `profile`, and `diff`.
- Add strict scan-graph mismatch gate (`exit=25`) and Phase31 regression.

## Direct Code Impact
- `prompt-dsl-system/tools/scan_graph.py` (new)
- `prompt-dsl-system/tools/hongzhi_plugin.py`
- `prompt-dsl-system/tools/module_profile_scanner.py`
- `prompt-dsl-system/tools/cross_project_structure_diff.py`
- `prompt-dsl-system/tools/golden_path_regression.sh`

## Contract Impact (Additive)
- `capabilities.json` / `capabilities.jsonl` add `scan_graph` object.
- `hongzhi_ai_kit_summary` add:
  - `scan_graph_used`
  - `scan_cache_hit_rate`
  - `java_files_indexed`
  - `bytes_read`
- New strict exit path: `25` when scan_graph spot-check mismatch is detected.

## Risk Surface
- Discover parsing path switched to scan graph source; fallback full parser is retained for uncertain controller files.
- New command `scan-graph` added and governance-gated.
- Diff/profile behavior changed when `--scan-graph` is provided.

## Guardrails Preserved
- Governance deny (`10/11/12/13`) still blocks command execution before writes.
- Read-only snapshot guard remains full-snapshot and unchanged for target repo write detection.
- Outputs remain workspace/state only.
