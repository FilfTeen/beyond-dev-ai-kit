# AUTO_ACK_HINT ChangeLog

## Modified / Added Files
- `prompt-dsl-system/tools/run.sh`
- `prompt-dsl-system/tools/pipeline_runner.py`
- `prompt-dsl-system/tools/risk_gate.py`
- `prompt-dsl-system/tools/token_recency.py` (new)
- `prompt-dsl-system/tools/README.md`
- `prompt-dsl-system/tools/AUTO_ACK_HINT_TEST_NOTES.md` (new)

## Behavior Changes
1. `run.sh` post-block hint
- Detects runner exit code `4` (risk gate block).
- Checks freshness of `RISK_GATE_TOKEN.json` via `token_recency.py`.
- Prints shortest unblock hint:
  - rerun with `--ack-latest`
  - alternative `--ack-file prompt-dsl-system/tools/RISK_GATE_TOKEN.json`

2. Optional one-shot auto retry
- New option: `--auto-ack-latest` (default off).
- On exit `4`, run.sh retries once with latest token.
- No retry loop: maximum one retry.

3. New wrapper options
- `--ack-latest`
- `--ack-file <path>`
- `--ack-hint-window <seconds>` (default `10`)
- `--no-ack-hint`

4. `pipeline_runner.py` risk block observability
- On risk gate block, stderr now includes:
  - `NEXT_CMD: ...`
- `run` supports `--risk-token-json-out` (default `prompt-dsl-system/tools/RISK_GATE_TOKEN.json`).

5. `risk_gate.py` token/report outputs
- Adds `RISK_GATE_TOKEN.json` output (`--token-json-out`).
- `risk_gate_report.json` now includes:
  - `next_cmd`
  - `next_cmd_ack_file`
  - `token_json_out`

## Default Safety Policy
- Default remains safe and manual:
  - no auto retry unless `--auto-ack-latest` is explicitly set
  - no silent bypass of risk gate
  - ACK token still required for high-risk continuation

