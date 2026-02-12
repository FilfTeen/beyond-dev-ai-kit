# R27 Perf Notes

## Summary
R27 focuses on output determinism and machine-line contract robustness; runtime scan cost remains equivalent to R26.

## Observations
- Added deterministic sorting is O(n log n) over already small output arrays (`artifacts`, `roots`, `candidates`).
- No additional full-repo scans introduced.
- Read command path resolution remains zero-touch (no probe file I/O).

## Validation
- Phase33 determinism checks pass across repeated discover runs.
- Existing performance-related phases (Phase30/Phase31) remain PASS.
