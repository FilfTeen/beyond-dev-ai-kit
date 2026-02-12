# Testdata Layout

This directory contains stable fixtures used by toolkit regression and smoke checks.

- `structure_cases/`: module-structure fixtures used by `golden_path_regression.sh` and scanner/plugin smoke phases.
- `verify_cases/`: follow-up verifier pass/warn/fail samples.
- `verify_followup/`: follow-up patch/scan verification samples.

Notes:

- These are versioned test assets, not runtime temp outputs.
- Runtime temp outputs should stay under `_regression_tmp*` (gitignored) or tool-specific cache directories.
