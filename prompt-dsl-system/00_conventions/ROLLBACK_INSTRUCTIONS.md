# Rollback Instructions (Constitution Upgrade)

Use this procedure when validation or run acceptance fails.

## Preconditions
- Work only inside `prompt-dsl-system/**`.
- Keep baseline snapshots intact:
  - `prompt-dsl-system/05_skill_registry/BASELINE_REGISTRY_SNAPSHOT.json`
  - `prompt-dsl-system/04_ai_pipeline_orchestration/BASELINE_PIPELINE_SNAPSHOT.json`

## Step 1 - Restore `skills.json`
1. Read `BASELINE_REGISTRY_SNAPSHOT.json`.
2. Write `skills_json_backup` back to `prompt-dsl-system/05_skill_registry/skills.json`.

## Step 2 - Restore pipeline files
1. Read `BASELINE_PIPELINE_SNAPSHOT.json`.
2. For each entry in `pipelines[]`, write `content_backup` back to the `pipeline` path.

## Step 3 - Move deprecated skills back to active tree
1. For each file under `prompt-dsl-system/05_skill_registry/deprecated/skills/<domain>/*.yaml`, move/copy back to:
   - `prompt-dsl-system/05_skill_registry/skills/<domain>/`
2. Remove deprecation header lines if original content parity is required:
   - `# DEPRECATED: ...`
   - `# Suggested mode: ...`
   - `# Mapping hints: ...`
   - `# Original name: ...`

## Step 4 - Re-run checks
1. Validate:
```bash
./prompt-dsl-system/tools/run.sh validate --repo-root .
```
2. Optional run checks:
```bash
./prompt-dsl-system/tools/run.sh run --repo-root . --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md
```

## Step 5 - Gate with ops_guard
```bash
/usr/bin/python3 prompt-dsl-system/tools/ops_guard.py --repo-root . --allowed-root prompt-dsl-system
```

## Expected rollback success criteria
- `validate` returns `Errors=0`, `Warnings=0`.
- Restored pipelines reference baseline skills.
- `skills.json` equals baseline snapshot registry content.
