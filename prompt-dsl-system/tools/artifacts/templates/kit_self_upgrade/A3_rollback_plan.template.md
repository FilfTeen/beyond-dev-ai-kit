# A3 Rollback Plan (Template)

## Rollback Trigger

- trigger_signal: `<gate_fail|regression_fail|manual_stop>`
- detection_evidence: `<log/report path>`

## Rollback Scope

- target: `prompt-dsl-system/**`
- changed_files_count: `<N>`

## Steps

1. Restore changed files from baseline:
- `<git restore / backup restore command>`
2. Re-run minimum gates:
- `./prompt-dsl-system/tools/run.sh validate -r .`
- `/usr/bin/python3 prompt-dsl-system/tools/pipeline_contract_lint.py --repo-root . --fail-on-empty`
3. Confirm machine contract:
- `/usr/bin/python3 prompt-dsl-system/tools/contract_validator.py --schema prompt-dsl-system/tools/contract_schema_v2.json --baseline-schema prompt-dsl-system/tools/contract_schema_v1.json --file <machine_log>`

## Verification

- expected_state: `<what should be restored>`
- post_rollback_checks: `<pass|fail>`
