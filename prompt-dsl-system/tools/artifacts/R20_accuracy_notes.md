# R20_accuracy_notes

## Calibration Decision Model
- Input sources:
  - discover candidate scores/confidence
  - structure-level counts (controller/service/repository/template/endpoint)
  - ambiguity metrics (`ambiguity_ratio`, `top2_score_ratio`)
  - operator hints (`--keywords`)
- Output core:
  - `needs_human_hint` (bool)
  - `confidence` (0~1)
  - `confidence_tier` (`high|medium|low`)
  - `reasons[]` (enum)
  - `suggested_hints`

## Reasons Enum (R20)
- `AMBIGUITY_RATIO_HIGH_NO_HINTS`
- `TOP2_SCORE_RATIO_AMBIGUOUS`
- `CONTROLLER_WITHOUT_ENDPOINTS`
- `CONFIDENCE_BELOW_MIN`
- `NO_MODULE_CANDIDATES`

## Default Thresholds
- `--min-confidence`: `0.60`
- `--ambiguity-threshold`: `0.80`

## Strict/Non-strict Behavior
- strict + `needs_human_hint=true` -> `exit=21`
- non-strict + `needs_human_hint=true` -> `exit=0` with warning marker and summary fields

## Workspace Artifacts (only)
- `calibration/calibration_report.json`
- `calibration/calibration_report.md`
- `calibration/hints_suggested.yaml` (unless `--no-emit-hints`)

## Notes on Explainability
- Calibration layer is non-destructive: it does not overwrite module discovery conclusions.
- It only annotates reliability and provides minimal hints for declared profile backfill.
