# Project Tech Stack Spec

## Purpose

Define a fact-first, auditable technical stack knowledge base for each project.

This spec is used by:

- `pipeline_project_stack_bootstrap.md`
- `project_stack_scanner.py`
- project bootstrap and migration planning flows

## File layout

```text
prompt-dsl-system/project_stacks/<project_key>/stack_profile.yaml                # declared (human curated)
prompt-dsl-system/project_stacks/<project_key>/stack_profile.discovered.yaml     # scanner generated
prompt-dsl-system/project_stacks/template/stack_profile.yaml                      # template
```

## Rules

1. Never guess stack facts. Every non-user-provided item must have scanner evidence.
2. If evidence is missing, mark the item `confidence: low` and add `required_additional_information`.
3. `stack_profile.discovered.yaml` is generated and should not be hand-edited.
4. If declared and discovered conflict, keep both and add `reconciliation_notes` instead of silent overwrite.

## Required fields (declared)

```yaml
profile_kind: "declared"
profile_version: "1.0"
identity:
  project_key: "<project_key>"
  project_name: "<human_name>"
  profile_id: "<project_key>/stack"
sources:
  - source_type: "user_input|scanner|thread_reference|document"
    summary: "where this fact came from"
stack:
  backend_languages: []
  backend_frameworks: []
  frontend_frameworks: []
  ui_frameworks: []
  mobile_frameworks: []
  database_engines: []
  process_engines: []
  build_tools: []
  vcs: []
constraints:
  java_runtime: "java8|unknown"
  sql_policy: "portable_first_dual_sql_when_needed"
confidence:
  overall: "low|medium|high"
  notes: []
required_additional_information: []
```

## Required fields (discovered)

```yaml
profile_kind: "discovered"
profile_version: "1.0"
identity:
  project_key: "<project_key>"
  profile_id: "<project_key>/stack"
discovery:
  generated_at: "<iso_timestamp>"
  scanner_version: "<scanner_version>"
  target_repo_root: "<abs_path>"
  file_count: <int>
  evidence:
    - signal: "pom.xml"
      detail: "spring-boot-starter-web"
      file: "<repo_relative_or_abs_path>"
stack:
  backend_languages: []
  backend_frameworks: []
  frontend_frameworks: []
  ui_frameworks: []
  mobile_frameworks: []
  database_engines: []
  process_engines: []
  build_tools: []
  vcs: []
confidence:
  overall: "low|medium|high"
  score: 0.0
  notes: []
required_additional_information: []
```

## Merge policy

`effective_stack = union(declared.stack, discovered.stack)` with evidence priority:

1. scanner evidence
2. repository documents
3. user input

Conflicts must be documented under `reconciliation_notes`.

## Output contract

Each stack bootstrap run should produce:

- `A1_stack_scan_evidence.md`
- `A2_stack_profile_diff.md`
- `A3_stack_rollback_plan.md`
- `A4_stack_cleanup_report.md`
