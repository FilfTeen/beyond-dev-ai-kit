# TRACE_DIFF Test Notes

## 用例 1：构造两个 trace（jsonl 模拟）
- 步骤：在 `prompt-dsl-system/tools/trace_history.jsonl` 追加两组不同 `trace_id` 记录（含 command/exit_code/verify_status）。
- 命令：
  ```bash
  ./prompt-dsl-system/tools/run.sh trace-index -r .
  ./prompt-dsl-system/tools/run.sh trace-diff -r . --a trace-open-hit-case-001 --b trace-dc6
  ```
- 结果：生成 `trace_diff.json` 与 `trace_diff.md`，可见 `latest_exit_code / blocked_by / verify_status / ack_usage` 差异。

## 用例 2：scan-deliveries=false（默认）
- 命令：
  ```bash
  ./prompt-dsl-system/tools/run.sh trace-diff -r . --a trace-open-hit-case-001 --b trace-dc6 --scan-deliveries false
  ```
- 预期：
  - `trace_diff.json.diff.deliveries_files.enabled=false`
  - 不扫描 deliveries 文件集合，仅比较路径级元信息。

## 用例 3：scan-deliveries=true + 截断
- 命令：
  ```bash
  ./prompt-dsl-system/tools/run.sh trace-diff -r . --a trace-open-hit-case-001 --b trace-dc6 --scan-deliveries true --deliveries-depth 2 --limit-files 20
  ```
- 预期：
  - 执行 deliveries 路径集合 diff
  - 当文件数超过 `limit-files` 时，`trace_diff.json.diff.deliveries_files.truncated=true`。

## 用例 4：前缀匹配歧义（latest=false）
- 命令：
  ```bash
  ./prompt-dsl-system/tools/run.sh trace-diff -r . --a trace- --b trace-open-hit-case --latest false
  ```
- 预期：
  - 输出候选列表
  - exit code=2（要求提供更精确 trace 前缀）。
