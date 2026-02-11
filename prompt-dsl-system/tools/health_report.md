# Health Report
- Generated at: 2026-02-11T09:37:58+08:00
- Repo root: /Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit
- Window: last 20 traces

## Build Integrity
- Registry entries: 1
- Pipelines checked: 9
- Validate: PASS (errors=0, warnings=0)
- Skills versions: 1.0.0 x1

## Execution Signals (last N)
- Commands: run=12, unknown=8
- Exit codes: 0=8, unknown=8, 4=3, 3=1
- Blocked by: none=16, verify_gate=3, loop_gate=1
- Verify status: MISSING=8, PASS=7, FAIL=5
- Ack usage: none=18, ack-latest=2

## Risk Triggers
- Top triggers:
  1) release_gate_bypass_attempt (2)
- Bypass attempts: 2

## Recommended Next Actions
1) Verify is failing in recent traces (5); run verify-followup-fixes and keep verify-gate=true.
2) Risk-gate blocks are frequent (exit 4: 3/20, 15%); reduce forbidden/outside-module triggers before retry.
3) Bypass attempts detected (2); stop push commands, resolve verify FAIL to PASS, and document rationale via --ack-note when exception is necessary.
