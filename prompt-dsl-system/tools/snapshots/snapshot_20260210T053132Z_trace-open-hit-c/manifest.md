# Snapshot Manifest
- snapshot_id: snapshot_20260210T053132Z_trace-open-hit-c
- created_at: 2026-02-10T05:31:32+00:00
- label: trace-open-hit
- context_id: ctx-open-hit-001
- trace_id: trace-open-hit-case-001
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
