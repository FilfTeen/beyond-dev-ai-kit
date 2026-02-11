# Snapshot Manifest
- snapshot_id: snapshot_20260210T052421Z_trace-index-open
- created_at: 2026-02-10T05:24:21+00:00
- label: trace-hit-test
- context_id: ctx-index-open-001
- trace_id: trace-index-open-001
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
