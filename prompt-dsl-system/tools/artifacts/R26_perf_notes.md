# R26 Performance Notes

## Focus
R26 keeps Round25 scan-graph performance gains and improves cross-command reuse determinism.

## Observed Behavior
- Discover cold run builds scan graph and reports scan IO counters.
- Profile/diff default reuse now backtracks latest discover scan graph when latest pointer references non-discover command.
- Profile/diff hot-path counters now represent command-local work:
  - `java_files_indexed=0`
  - `bytes_read=0`

## Why this matters
- Removes false "rescan" impression in profile/diff summaries.
- Keeps source graph statistics in additive fields for auditability.

## Suggested Monitoring Fields
- Summary line:
  - `scan_graph_used`
  - `scan_cache_hit_rate`
  - `java_files_indexed`
  - `bytes_read`
- Capabilities:
  - `scan_graph.*`
  - `scan_io_stats.*`
