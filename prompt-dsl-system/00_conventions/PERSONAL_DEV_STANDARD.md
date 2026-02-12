# Personal Dev Standard (C++-Aligned, Team-Compatible)

Scope: Hongzhi company-domain work under `prompt-dsl-system/**` and downstream project tasks.

## Priority

1. Team/system constraints first (boundary, governance, compatibility, safety).
2. This personal standard second.
3. Convenience last.

## Naming

- Use English-only names with stable semantics.
- One concept, one name across module boundaries.
- Class/type: `UpperCamelCase`.
- Java public API methods: `lowerCamelCase`.
- Internal helper names (new local utilities/scripts): `lower_snake_case`.
- Constants: `UPPER_SNAKE_CASE`.
- Boolean fields/methods: prefix `is_`, `has_`, `can_` (or Java camel equivalent).
- SQL identifiers/aliases/DB fields: `lower_snake_case`.
- Prohibit pinyin abbreviations and invented short words.

## Design and implementation style

- Prefer minimal, composable functions with explicit inputs/outputs.
- Prefer additive change over broad rewrite unless root-cause requires rewrite.
- Keep module boundaries strict; avoid touching shared/system paths unless explicitly allowed.
- Any uncertainty must be resolved by scan/evidence, not assumption.

## Quality gates

Before completion, always ensure:

- impact tree present
- change ledger present
- rollback plan present
- cleanup report present
- validate/guard checks executed or explicitly reported as not run

## SQL and compatibility

- Portable SQL first.
- If not portable, provide dual SQL (Oracle + MySQL) and document routing.
- Business logic around SQL must stay cross-dialect compatible.

## Self-monitoring

Trigger self-correction when:

- same file edited repeatedly without convergence
- same failure repeats more than twice
- changed files drift outside intended module boundary

Action sequence:

1. pause write operations
2. re-scan root cause chain
3. rollback wrong partial edits
4. resume with narrowed scope
