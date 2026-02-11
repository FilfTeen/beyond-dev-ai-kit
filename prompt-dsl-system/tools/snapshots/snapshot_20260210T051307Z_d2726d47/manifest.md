# Snapshot Manifest
- snapshot_id: snapshot_20260210T051307Z_d2726d47
- created_at: 2026-02-10T05:13:07+00:00
- label: test-restore-guide
- context_id: None
- trace_id: None
- vcs: none

## Artifacts
- status: status.txt
- changed_files: changed_files.txt
- diff: diff.patch
- inputs_dir: inputs/

## Skipped
- missing_inputs: 0
- skipped_large_files: 0
- copy_errors: 0
- diff_unavailable_reason: no vcs detected

## Restore Hints
- Full restore (git, destructive): `git reset --hard && git clean -fd`
- Partial restore (git): `git restore -- <path>` (or `git checkout -- <path>` on old git)
- Full restore (svn): `svn revert -R .`
- Partial restore (svn): `svn revert <path>`
- If no VCS: use snapshot diff + inputs to apply manual rollback.
