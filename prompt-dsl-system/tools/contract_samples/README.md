# Contract Sample Logs

This directory contains replayable machine-line sample logs for contract validator checks.

## Files

- `sample_kit_caps_v2.log`
- `sample_hongzhi_caps_v2.log`
- `sample_hongzhi_gov_block_v2.log`
- `replay_contract_samples.sh`

## Replay

```bash
bash prompt-dsl-system/tools/contract_samples/replay_contract_samples.sh --repo-root .
```

Validation strategy:

- Prefer `contract_schema_v2.json`.
- When v2 exists, enforce additive baseline guard against `contract_schema_v1.json`.
