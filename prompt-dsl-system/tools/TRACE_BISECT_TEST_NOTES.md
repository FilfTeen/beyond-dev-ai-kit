# TRACE_BISECT Test Notes

## 用例 1：good 自动选择成功
- 命令：
  ```bash
  ./prompt-dsl-system/tools/run.sh trace-bisect -r . --bad trace-dc6
  ```
- 预期：
  - 自动选取 bad 之前最近的 `verify_top=PASS` 且 `latest_exit_code=0` trace 作为 good。
  - 生成：`bisect_plan.json/md/sh`。

## 用例 2：good 缺失时提示
- 前置：当 index 内找不到满足条件的 PASS 历史（或人为传入无法匹配 bad 时间线的样本）
- 命令：
  ```bash
  ./prompt-dsl-system/tools/run.sh trace-bisect -r . --bad trace-unknown --auto-find-good true
  ```
- 预期：
  - 若 bad 不存在，exit 2。
  - 若 bad 存在但 good 不可选，`bisect_plan.json` 含 `good_missing=true`，并在 stderr 给出手工指定 `--good` 提示。

## 用例 3：bypass_attempt 触发优先走 P0
- 前置：bad trace 的 `highlights.bypass_attempt=true`，或 `verify_top=FAIL` 且 `ack_total>0`。
- 命令：
  ```bash
  ./prompt-dsl-system/tools/run.sh trace-bisect -r . --bad trace-dc6cd01395f14cd2b762229630586cda
  ```
- 预期：
  - `bisect_plan.md` 中前序步骤优先出现 P0（trace-open bad、verify-followup-fixes、受控 run）。

## 用例 4：DRY_RUN 脚本安全性
- 命令：
  ```bash
  bash prompt-dsl-system/tools/bisect_plan.sh
  ```
- 预期：
  - 默认 `DRY_RUN=1` 仅打印命令，不执行。
  - 含 `<MODULE_PATH>` 等变量的步骤会先检查变量，不满足时 `exit 2`。
