# AUTO_ACK_HINT Test Notes

## Scope
- repo: `beyond-dev-ai-kit`
- changed area: `prompt-dsl-system/tools/**`
- objective: verify risk-gate block hint + optional auto retry behavior in `run.sh`

## Case 1: Trigger gate -> run.sh prints shortest continue hint
- Command:
```bash
./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system/tools \
  --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md \
  --trace-id trace-gatehint-readable \
  --context-id ctx-gatehint-readable-run \
  --out prompt-dsl-system/tools/run_plan_autoack_gate_readable.yaml
```
- Setup: pre-seeded `trace_history.jsonl` with repeated same-trace records to force loop HIGH.
- Expected:
  - exit `4`
  - output contains:
    - `NEXT_CMD: ... --ack-latest` (from `pipeline_runner.py`)
    - `[hongzhi][RISK-GATE] Token issued...` (from `run.sh`)
    - `or use --ack-file prompt-dsl-system/tools/RISK_GATE_TOKEN.json`
- Actual: matched expected (exit `4` + both hint lines observed).

## Case 2: `--auto-ack-latest` retries once automatically
- Command:
```bash
./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system/tools \
  --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md \
  --trace-id trace-autoack-retry \
  --context-id ctx-autoack-retry-run \
  --out prompt-dsl-system/tools/run_plan_autoack_retry.yaml \
  --auto-ack-latest
```
- Setup: pre-seeded same-trace loop HIGH.
- Expected:
  - first attempt blocked by risk gate
  - run.sh uses latest token and retries once
  - second attempt passes (or fails once and returns `4` without looping)
- Actual:
  - first attempt blocked (HIGH)
  - auto retry executed once
  - final exit `0` (run plan generated)

## Case 3: `--no-ack-hint` suppresses hint output
- Command:
```bash
./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system/tools \
  --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md \
  --trace-id trace-noackhint \
  --context-id ctx-noackhint-run \
  --out prompt-dsl-system/tools/run_plan_noackhint.yaml \
  --no-ack-hint
```
- Setup: pre-seeded same-trace loop HIGH.
- Expected:
  - exit `4`
  - no `[hongzhi][RISK-GATE] Token issued...` hint lines
- Actual: matched expected (exit `4`, no hint lines).

## Extra Sanity
- `--ack-latest` compatibility check:
```bash
./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system/tools \
  --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md \
  --trace-id trace-noackhint \
  --context-id ctx-noackhint-run \
  --out prompt-dsl-system/tools/run_plan_noackhint.yaml \
  --ack-latest
```
- Actual: exit `0` (token loaded from `RISK_GATE_TOKEN.json` and accepted).

