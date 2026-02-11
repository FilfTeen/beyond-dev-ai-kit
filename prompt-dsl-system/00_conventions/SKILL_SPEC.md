# Skill Spec

## Core Sources

- Single skill source of truth: one YAML file per skill.
- Registry source for discovery: `skills.json` generated from YAML metadata.

## Naming Rule

- Every skill name MUST follow: `skill_<domain>_<verb>_<object>`.
- `<domain>` must match the registry folder domain.
- Names must be unique across the registry.

## Required YAML Schema

Each skill YAML MUST include:

- `name`
- `description`
- `version`
- `domain`
- `tags`
- `parameters`
- `prompt_template`
- `output_contract`
- `examples`

## Unified Output Contract

Every skill output MUST use this structure:

- `summary`
- `artifacts[]`
- `risks[]`
- `next_actions[]`

## Registry Contract

- File: `prompt-dsl-system/05_skill_registry/skills.json`
- JSON shape:
  - `name`
  - `description`
  - `version`
  - `domain`
  - `tags[]`
  - `path` (repository-relative skill YAML path)
  - `status` (optional, default `"deployed"` for backward compatibility)
- Registry entries MUST map 1:1 to YAML skill files.

## Skill Status Lifecycle

Valid status values: `staging` | `deployed` | `deprecated`

| Status | Meaning | Rules |
| --- | --- | --- |
| `staging` | Under development, not production-ready | Default for newly generated skills. May be promoted after audit PASS + human approval. |
| `deployed` | Production-ready, fully audited | Existing skills without explicit status are treated as `deployed`. |
| `deprecated` | No longer active, archived | Must be moved to `skills/deprecated/`. Must not be modified. |

Promotion flow:

1. New skill created → `status: staging`
2. `skill_template_audit.py --scope staging` → PASS
3. Human review confirms readiness
4. Update `skills.json` entry: `status: "deployed"`

Backward compatibility: if `status` field is absent, reader MUST treat it as `"deployed"`.

## Global Trace Parameters (Mandatory for All Skills)

- `context_id`: `string` (optional). If not provided, the executor may generate one.
- `trace_id`: `string` (optional, recommended). Should be unique for each pipeline run.

## Objective Template (Preferred Contract)

Skills and pipeline calls should prioritize the following objective template (Markdown or YAML block):

- `inputs`: Input sources (file paths/snippets/APIs/tables).
- `constraints`: Constraints (for example: no schema change, syntax-only migration, compatibility and performance limits).
- `acceptance`: Acceptance criteria (required artifacts and checks).
- `forbidden`: Prohibited actions (forbidden paths, cross-module edits, sensitive data leakage).

Template example:

```yaml
inputs: "<MODULE_PATH>/..."
constraints: "No schema changes; syntax-only conversion where required."
acceptance: "Return numbered artifacts and verification evidence."
forbidden: "No cross-module edits; no secret disclosure."
```

## Artifact Handoff Contract (Mandatory)

- Every skill output must number artifacts explicitly: `A1`, `A2`, `A3`...
- `artifacts.name` should include numbered prefixes (for example: `A1_migration_sql`, `A2_risk_list`).
- Downstream steps must reference upstream artifacts through `input_artifact_refs` (array of artifact ids).

## Company Profile Injection Rules

- Company profile source of truth: `prompt-dsl-system/company_profile.yaml`.
- Runner may inject defaults only when the following parameters are missing from a step:
  - `schema_strategy`
  - `execution_tool`
  - `require_precheck_gate`
- Injection policy is additive-only:
  - Missing fields can be filled from company profile defaults.
  - User-provided parameters must not be overwritten.

## Company Constitution Binding

- Company-domain execution must follow: `prompt-dsl-system/00_conventions/HONGZHI_COMPANY_CONSTITUTION.md`.
- Pipelines should include boundary/fact/safety controls through parameters and forbidden lists.
- If `allowed_module_root` is missing, only scan/risk assessment is allowed before user clarification.

## Skill Template Generation Contract

- Template location: `prompt-dsl-system/05_skill_registry/templates/skill_template/`
- Template contents:
  - `skill.yaml.template` — YAML skeleton with all required fields as `{{PLACEHOLDER}}`
  - `references/README.template` — rule stub for reference documents
  - `scripts/README.template` — rule stub for helper scripts
  - `assets/README.template` — rule stub for static assets
- Generation workflow (used by `pipeline_skill_creator` Step 3):
  1. Copy `templates/skill_template/` to `skills/<domain>/skill_<domain>_<verb>_<object>/`
  2. Rename `skill.yaml.template` → `skill_<domain>_<verb>_<object>.yaml`
  3. Rename all `README.template` → `README.md`
  4. Fill `{{PLACEHOLDER}}` values from Step 1 impact tree and Step 2 generation output
  5. Validate filled YAML against Required YAML Schema (above)
- Freedom level: **low** — template copy is deterministic, no creative decisions

## Bundled Resources Convention

Each skill MAY include bundled resource subdirectories:

```text
skills/<domain>/skill_<domain>_<verb>_<object>/
  skill_<domain>_<verb>_<object>.yaml
  references/     # domain knowledge, API mappings, architecture docs
  scripts/        # helper scripts (validate, migrate, convert)
  assets/         # static assets (diagrams, configs, sample data)
```

Rules:

- `references/` files >100 lines **MUST** include a Table of Contents (TOC) at the top.
- YAML parameter `read_refs: []` instructs agent which reference files to load.
- `scripts/` must be idempotent and support `--dry-run` by default.
- `assets/` binary files should be <1MB each.

## Progressive Disclosure

When `read_refs` lists reference files, agent behavior:

1. **Load TOC only** — read first 20 lines of each reference file.
2. **Navigate on demand** — read specific sections only when task objective requires them.
3. **Never expand all** — do not inline full reference content into the working context.
4. Meta mode behavior: when listing available resources, output a **navigation index** (file → TOC summary) rather than full content.

### NavIndex Output Format

When `read_refs` is non-empty, agent MUST produce `R*_ref_nav_index.md` containing:

```markdown
# Navigation Index

## <filename>
- **TOC** (first 20 lines summary)
- **Grep patterns**: `<pattern1>`, `<pattern2>` (for targeted section lookup)
- **Target paragraphs**: §<section_name> at L<start>-L<end>

## <filename2>
...
```

Each reference entry must include:

- TOC summary (extracted from first 20 lines)
- Grep patterns the agent used or recommends for section navigation
- Target paragraph locations with line ranges
