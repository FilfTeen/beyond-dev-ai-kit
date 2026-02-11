# Trace Diff (A vs B)
- A: trace-open-hit-case-001 (last_seen=2026-02-10T05:31:32+00:00, latest_exit=0, verify_top=PASS)
- B: trace-dc6cd01395f14cd2b762229630586cda (last_seen=2026-02-10T04:41:10+00:00, latest_exit=4, verify_top=FAIL)

## Key Changes
- Exit code: A=0 -> B=4 (changed=True)
- Verify: A=PASS -> B=FAIL (changed=True)
- Blocked-by net: {'none': -1, 'verify_gate': 1}
- Ack usage: A=0 -> B=0
- Snapshots delta (B-A): -1

## Deliveries (optional)
- Enabled: True
- Added: 0
- Removed: 1
- Common count: 0
- Truncated: False
- Removed top 20:
  - README.txt

## Recommended Next Actions
1) B 出现 verify FAIL（A 无 FAIL）：先执行 trace-open 定位，再跑 verify-followup-fixes 与 apply-followup-fixes(plan) 收敛残留引用。
2) 阻断型 gate 增加或成功执行减少：优先运行 debug-guard，并减少同一问题的反复推进尝试。
3) B 最新退出码非 0（A 为 0）：先看 B 的 health_report 与 risk_gate_report，再决定是否继续 run/apply。
