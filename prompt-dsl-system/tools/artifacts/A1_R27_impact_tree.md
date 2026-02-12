# A1 R27 Impact Tree

## Scope
- Minimal intrusive updates under `prompt-dsl-system/**`.
- No contract removals; additive-only output extensions.

## Change Branches
1. Machine-line JSON unification
- Files: `prompt-dsl-system/tools/hongzhi_plugin.py`
- Impact:
  - unified `json='...'` encoding path for all machine lines
  - CLI toggle `--machine-json=0|1` + env override `HONGZHI_MACHINE_JSON_ENABLE`

2. Deterministic output ordering
- Files: `prompt-dsl-system/tools/hongzhi_plugin.py`
- Impact:
  - stable sort for `artifacts[]`, `roots[]`, `metrics.candidates[]`

3. Mismatch explainability tightening
- Files: `prompt-dsl-system/tools/hongzhi_plugin.py`, `prompt-dsl-system/tools/scan_graph.py`
- Impact:
  - enum-constrained `mismatch_reason`
  - additive `mismatch_suggestion`

4. Read-command zero-touch normalization
- Files: `prompt-dsl-system/tools/hongzhi_ai_kit/paths.py`
- Impact:
  - explicit read-only/writable root resolution wrappers
  - no probe-file behavior for `status/index` retained

5. Regression expansion
- Files: `prompt-dsl-system/tools/golden_path_regression.sh`
- Impact:
  - new Phase33 (6 checks) for roundtrip parse/no-newline/determinism/mismatch enum/zero-touch
