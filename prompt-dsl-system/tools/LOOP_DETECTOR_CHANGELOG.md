# LOOP_DETECTOR_CHANGELOG

## 新增/修改文件清单
- 新增：`prompt-dsl-system/tools/loop_detector.py`
- 新增：`prompt-dsl-system/tools/trace_history.jsonl`
- 修改：`prompt-dsl-system/tools/pipeline_runner.py`
- 修改：`prompt-dsl-system/tools/run.sh`
- 修改：`prompt-dsl-system/tools/README.md`
- 新增：`prompt-dsl-system/tools/LOOP_DETECTOR_TEST_NOTES.md`
- 新增：`prompt-dsl-system/tools/LOOP_DETECTOR_CHANGELOG.md`

## 规则摘要
`loop_detector.py` 在最近窗口（默认 N=6）内执行以下检测：
1. A 文件集绕圈（HIGH）：
   - changed_files Jaccard 持续 >= 0.7
   - 且 fail 反复出现或 violations 不下降
2. B 越界冲动（MEDIUM）：
   - 最近窗口 violations_count>=1 的次数 >=3
3. C 影响域扩张（MEDIUM）：
   - 最近 3 次 changed_files_count 单调上升且增幅 >=50%
4. D 缺少 module_path 盲跑（MEDIUM）：
   - effective_module_path=null

## 默认策略（安全）
- `run` 完成后自动执行 loop 检测。
- 若 level=MEDIUM/HIGH：
  - 输出警告
  - 自动触发 advisory debug-guard
  - 自动生成/刷新 move/rollback plans
- 默认不阻断（`--fail-on-loop` 未开启）。

## 强制阻断策略
- 开启：`--fail-on-loop`
- 仅在 `level=HIGH` 时阻断
- 退出码：`--loop-exit-code`（默认 `3`）
- trace action：`loop_blocked`

## 回滚方式
1. 查看 `loop_diagnostics.md` 和 `guard_report.json`。
2. 优先使用 `apply-move` 纠正越界：
   - `./prompt-dsl-system/tools/run.sh apply-move -r . -m <MODULE_PATH> --yes --move-dry-run false`
3. 若仍失败，执行 rollback 方案：
   - `./prompt-dsl-system/tools/run.sh rollback -r . -m <MODULE_PATH> --report prompt-dsl-system/tools/guard_report.json`
