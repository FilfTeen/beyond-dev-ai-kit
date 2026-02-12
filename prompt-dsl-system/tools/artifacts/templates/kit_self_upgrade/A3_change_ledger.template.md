# A3 Change Ledger (Template)

## Scope

- target: `prompt-dsl-system/**`
- context_id: `<CTX_ID>`
- trace_id: `<TRACE_ID>`
- window: `<START_UTC> ~ <END_UTC>`

## File Changes

| Path | Type | Why | Impact |
|---|---|---|---|
| `<file_path>` | `<add|modify|delete>` | `<reason>` | `<behavioral impact>` |

## Risk & Mitigation

- risk_level: `<low|medium|high>`
- risk_detail: `<what can break>`
- mitigation: `<how to control>`

## Validation Evidence

- `./prompt-dsl-system/tools/run.sh validate -r .` : `<pass|fail>`
- `/usr/bin/python3 prompt-dsl-system/tools/pipeline_contract_lint.py --repo-root . --fail-on-empty` : `<pass|fail>`
- `/usr/bin/python3 prompt-dsl-system/tools/skill_template_audit.py --repo-root . --scope all --fail-on-empty` : `<pass|fail>`
- `./prompt-dsl-system/tools/run.sh self-upgrade -r . --strict-self-upgrade` : `<pass|fail>`

## Notes

- bypass_used: `<none|HONGZHI_ALLOW_RUN_WITHOUT_MODULE_PATH=1>`
- strict_self_upgrade: `<enabled|disabled>`
