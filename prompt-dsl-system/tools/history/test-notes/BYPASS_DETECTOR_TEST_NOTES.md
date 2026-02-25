# BYPASS_DETECTOR_TEST_NOTES

## Scope
- Repo: `beyond-dev-ai-kit`
- Date: 2026-02-10 (UTC)
- Toolchain: `/usr/bin/python3`, `prompt-dsl-system/tools/run.sh`

## Case 1: 构造 verify FAIL

### Command
```bash
cat > prompt-dsl-system/tools/followup_verify_report.json <<'JSON'
{
  "repo_root": ".",
  "generated_at": "2026-02-10T00:00:00Z",
  "summary": {
    "status": "FAIL",
    "hits_total": 42,
    "gate_recommended": true,
    "gate_reason": "status=FAIL"
  }
}
JSON
```

### Expected
- 后续推进型命令触发 verify gate（默认 `verify-threshold=FAIL`）。

### Actual
- 生效；后续 `run` 首次执行被 risk/verify gate 阻断，exit=4。

---

## Case 2: 连续推进尝试触发 bypass 检测（LOOP_HIGH）

### Commands
```bash
# 1) 无 ACK，先触发 gate token
./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system \
  --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md \
  --risk-gate false --verify-gate true --verify-threshold FAIL

# 2) ACK 推进一次（写入 bypass 证据）
./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system \
  --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md \
  --risk-gate false --verify-gate true --verify-threshold FAIL \
  --ack-latest --ack-note "test bypass attempt note"

# 3) 再次 ACK 推进尝试（token 已消费，重新阻断）
./prompt-dsl-system/tools/run.sh run -r . -m prompt-dsl-system \
  --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md \
  --risk-gate false --verify-gate true --verify-threshold FAIL \
  --ack-latest

# 4) 运行 loop_detector 汇总窗口证据
/usr/bin/python3 prompt-dsl-system/tools/loop_detector.py \
  --repo-root . \
  --history prompt-dsl-system/tools/trace_history.jsonl \
  --pipeline-path prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_sql_oracle_to_dm8.md \
  --effective-module-path prompt-dsl-system \
  --window 6 \
  --same-trace-only false \
  --output-dir prompt-dsl-system/tools
```

### Expected
- `loop_diagnostics.json` 触发 `release_gate_bypass_attempt` 且 `level=HIGH`。

### Actual
- 命中：`level=HIGH`
- 触发器：`release_gate_bypass_attempt`
- 证据：`evidence.recent_attempts` 记录到 2 条推进尝试。

---

## Case 3: risk_gate 禁止 auto-ack（bypass 高风险）

### Command
```bash
/usr/bin/python3 prompt-dsl-system/tools/risk_gate.py \
  --repo-root . \
  --guard-report prompt-dsl-system/tools/guard_report.json \
  --loop-report prompt-dsl-system/tools/loop_diagnostics.json \
  --move-report prompt-dsl-system/tools/move_report.json \
  --verify-report prompt-dsl-system/tools/followup_verify_report.json \
  --verify-threshold FAIL \
  --verify-as-risk true \
  --verify-required-for run \
  --command-name run \
  --threshold HIGH \
  --mode check
```

### Expected
- 阻断（exit=4）
- `risk_gate_report.json` 中 `auto_ack_allowed=false`
- deny reason 为 bypass 专用文案。

### Actual
- 阻断：exit=4
- `auto_ack_allowed=false`
- `auto_ack_denied_reason="verification failed and repeated bypass attempts detected; manual ack required"`

---

## Case 4: ack-note 落盘

### Evidence
- 文件：`prompt-dsl-system/tools/ack_notes.jsonl`
- 存在记录（节选）：
  - `command=run`
  - `note="test bypass attempt note"`
  - `verify_hits_total=42`

### Expected
- verify FAIL + ACK 使用时支持审计备注写入。

### Actual
- 符合预期。

