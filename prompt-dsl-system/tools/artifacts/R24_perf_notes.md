# R24_perf_notes

## Performance-Oriented Changes
- Removed redundant second full layout adapter scan in discover path.
- Added `scan_io_stats` for auditability:
  - `layout_adapter_runs`
  - `java_files_scanned`
  - `templates_scanned`
  - `snapshot_files_count`
  - cache hit/miss metrics

## Concurrency Notes
- JSONL writes are lock-protected append operations with fsync.
- Capability/federated JSON writes now use unique temp files to avoid `.tmp` collision under parallel runs.

## Observed Regression Signal
- Phase30 `discover_io_reduction_same_output` PASS: output stability preserved with IO telemetry present.
- Phase30 `jsonl_append_concurrency_no_loss` PASS: 20 parallel runs produce 20 valid JSONL records.

## Suggested Defaults
- Keep `--smart` enabled for repetitive scans to reduce cold scan overhead.
- For large repos, use `--keywords` early to reduce ambiguity and scan fan-out.
