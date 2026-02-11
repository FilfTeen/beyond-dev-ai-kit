# Trace Bisect Plan
- Good: trace-bisect-good-001 (last_seen=2026-02-10T05:00:00+00:00, verify_top=PASS, latest_exit=0)
- Bad: trace-dc6cd01395f14cd2b762229630586cda (last_seen=2026-02-10T04:41:10+00:00, verify_top=FAIL, latest_exit=4)
- Why this plan:
  - verify_changed=True
  - blocked_by_delta={'none': -1, 'verify_gate': 1}
  - bypass_attempt=True

## Fill-in Guide
- <MODULE_PATH>: 例如 `src/main/java/com/indihx/ownercommittee`
- <PIPELINE_PATH>: 例如 `prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md`
- <MOVES_JSON>: 例如 `prompt-dsl-system/tools/moves_mapping_rename_suffix.json`
- <SCAN_REPORT_JSON>: 例如 `prompt-dsl-system/tools/followup_scan_report_rename_suffix.json`

## Steps (Shortest)
### S0 Generate diff evidence
```bash
./prompt-dsl-system/tools/run.sh trace-diff -r . --a trace-bisect-good-001 --b trace-dc6cd01395f14cd2b762229630586cda --scan-deliveries false
```
Expected: trace_diff.md generated with key deltas
Stop if: Diff shows verify FAIL spike or guard/loop gate increase

### S1 Inspect bypass evidence for bad trace
```bash
./prompt-dsl-system/tools/run.sh trace-open -r . --trace-id trace-dc6cd01395f14cd2b762229630586cda
```
Expected: risk/verify context displayed
Stop if: release_gate_bypass_attempt confirmed

### S2 Force verification before any further promotion
```bash
./prompt-dsl-system/tools/run.sh verify-followup-fixes -r . --moves <MOVES_JSON>
```
Expected: verify report reaches PASS or WARN
Stop if: verify still FAIL

### S3 Re-check release gate with loop protection
```bash
./prompt-dsl-system/tools/run.sh run -r . -m <MODULE_PATH> --pipeline <PIPELINE_PATH> --verify-gate true --fail-on-loop true
```
Expected: no bypass warning, controlled gate outcome
Stop if: risk gate still requests ACK under FAIL

### S4 Generate follow-up patch plan (plan only)
```bash
./prompt-dsl-system/tools/run.sh apply-followup-fixes -r . --scan-report <SCAN_REPORT_JSON> --mode plan
```
Expected: followup_patch_plan.json generated
Stop if: no safe high-confidence replacements

If you must ACK
- 建议追加 `--ack-note` 记录放行理由。
- 先生成 `snapshot-restore-guide`，再考虑 ACK 推进。
