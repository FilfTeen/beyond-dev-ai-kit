# Snapshot Restore Guide
- Snapshot: `snapshot_20260210T051307Z_d2726d47`
- Created at: `2026-02-10T05:13:07+00:00`
- Trace ID: `None`
- Label: `test-restore-guide`
- Snapshot dir: `/Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit/prompt-dsl-system/tools/snapshots/snapshot_20260210T051307Z_d2726d47`
- VCS: `none`
- Strict mode: `True`

## Current Repo Check
- Status: **PASS**
- Warnings: none

## Recommended Order
1. 优先按文件回滚：`restore_files.sh`
2. 若仍不一致，再做全量回滚：`restore_full.sh`

## Commands
```bash
# preview only (default)
/Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit/prompt-dsl-system/tools/snapshots/snapshot_20260210T051307Z_d2726d47/restore/restore_files.sh
# execute for real
DRY_RUN=0 /Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit/prompt-dsl-system/tools/snapshots/snapshot_20260210T051307Z_d2726d47/restore/restore_files.sh

# full restore preview
/Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit/prompt-dsl-system/tools/snapshots/snapshot_20260210T051307Z_d2726d47/restore/restore_full.sh
# full restore execute
DRY_RUN=0 /Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit/prompt-dsl-system/tools/snapshots/snapshot_20260210T051307Z_d2726d47/restore/restore_full.sh
```

## Inputs
- changed_files list: `prompt-dsl-system/tools/snapshots/snapshot_20260210T051307Z_d2726d47/changed_files.txt`
- diff patch: `diff.patch` (under snapshot dir)

## Troubleshooting
- svn tree conflicts: run `svn status`, resolve conflicts, then retry restore script.
- git untracked leftovers: after review, use `git clean -fd` (destructive).
- strict mismatch: verify you are in the same repo root as snapshot manifest.
