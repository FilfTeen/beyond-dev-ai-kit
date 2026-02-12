# R25 Performance Notes

## Summary
Round25 introduces Unified Scan Graph v1 to avoid repeated full-content scans across discover/profile/diff.

## Mechanism
- First pass builds `scan_graph.json` + `scan_cache/<cache_key>.json`.
- Subsequent runs reuse cache by `cache_key` and reduce `bytes_read` for scan-stage parsing.
- Profile/diff can directly consume prior scan graph via explicit CLI flags.

## Key Metrics (from contract fields)
- `scan_graph.cache_hit_rate`
- `scan_graph.java_files_indexed`
- `scan_graph.bytes_read`
- `scan_io_stats.*`

## Round24 vs Round25 Comparison (sample fixture)
| Metric | Round24 (discover) | Round25 cold | Round25 warm |
| --- | ---: | ---: | ---: |
| `java_files_scanned` | 3 | 3 | 3 |
| `bytes_read` | n/a | ~806 | 0 |
| `scan_time_s` | ~0.014 | ~0.018 | ~0.010 |

Notes:
- Round24 did not expose explicit `bytes_read`; comparison uses nearest observable counters.
- Warm-run gains come from scan cache reuse and reduced parse I/O.
