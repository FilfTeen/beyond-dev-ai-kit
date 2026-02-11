# R19_perf_notes

## Limits Contract
- `--max-files <N>` and `--max-seconds <S>` now surface machine-visible limit state.
- strict mode (`--strict`) on limits hit => `exit=20`.
- non-strict mode on limits hit => `exit=0` with `limits_hit=true` and warning metadata.

## Suggested Defaults (pragmatic baseline)
- medium monorepo:
  - `--max-files 50000`
  - `--max-seconds 60`
- large monorepo:
  - `--max-files 120000`
  - `--max-seconds 180`

## Smart Reuse
- On cache/state continuity, `--smart` keeps second-run latency low and emits:
  - summary `smart_reused=1`
  - capabilities `smart.reused=true` with `reused_from_run_id`

## Bench Snapshot (Regression Fixtures)
- Regression Phase25 confirms both limits paths:
  - normal mode: `limits_hit=1`, `exit=0`
  - strict mode: `limits_hit=1`, `exit=20`
