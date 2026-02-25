# tools history index

This directory stores archived historical documents from `prompt-dsl-system/tools`.

## retention policy

- Keep only the most recent three version windows for round-based artifacts.
- Current kept rounds: `R27`, `R28`, `R29`.
- Remove older round files after archive verification.

## subdirectories

- `changelog/`: archived `*_CHANGELOG.md` files.
- `test-notes/`: archived `*_TEST_NOTES.md` files.
- `artifacts/`: historical notes and migration records.
- `run-plans/`: archived static run plan snapshots.

## lookup order

1. Check active docs in `prompt-dsl-system/tools/README.md`.
2. Check `history/README.md` and subdirectory indexes.
3. Only then search older commits.
