# Machine Contract Compatibility Strategy (v1 -> v2)

## Objective

- Keep machine-line contract evolution backward compatible for agent chaining.
- Allow new contract versions while preserving existing parser expectations.

## Current Baseline

- `prompt-dsl-system/tools/contract_schema_v1.json`:
  - baseline schema for `HONGZHI_*` and `KIT_CAPS` machine lines.
- `prompt-dsl-system/tools/contract_schema_v2.json`:
  - current schema (additive evolution from v1).

## Compatibility Rules

1. Additive only:
- New contract versions may add machine lines or new optional fields.
- Existing machine line names and v1 `required_fields` must not be removed.

2. Stable semantics:
- Existing field names must keep meaning and value domain.
- Existing enum values remain valid; extensions are additive.

3. Validator guard:
- `contract_validator.py` supports `--baseline-schema` additive check.
- Strict self-upgrade preflight must validate v2 against v1 baseline.

4. Runtime fallback:
- Default validator schema selection prefers highest available (`v2 -> v1`).
- Explicit `--schema` remains supported for deterministic replay.

## Recommended Validation Commands

```bash
/usr/bin/python3 prompt-dsl-system/tools/contract_validator.py \
  --schema prompt-dsl-system/tools/contract_schema_v2.json \
  --baseline-schema prompt-dsl-system/tools/contract_schema_v1.json \
  --file <machine_log.txt>
```

```bash
./prompt-dsl-system/tools/run.sh self-upgrade -r . --strict-self-upgrade
```
