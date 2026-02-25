# TRACE_DIFF Changelog

## 新增/修改文件清单
- 新增：`prompt-dsl-system/tools/trace_diff.py`
- 修改：`prompt-dsl-system/tools/pipeline_runner.py`
- 修改：`prompt-dsl-system/tools/run.sh`
- 修改：`prompt-dsl-system/tools/README.md`
- 新增：`prompt-dsl-system/tools/TRACE_DIFF_TEST_NOTES.md`
- 新增：`prompt-dsl-system/tools/TRACE_DIFF_CHANGELOG.md`

## 功能摘要
- 新增 `trace-diff` 子命令：对比 trace A/B 的命令分布、阻断分布、verify 状态、ack 使用、路径存在性差异。
- 支持 trace_id 前缀匹配：
  - `--latest true`（默认）自动取最新命中。
  - `--latest false` 若命中多条则输出候选并退出 2，避免误对比。
- 输出双报告：
  - `prompt-dsl-system/tools/trace_diff.json`
  - `prompt-dsl-system/tools/trace_diff.md`
- 可选 deliveries 集合 diff（默认关闭）：`--scan-deliveries true`。

## deliveries 扫描限制（防爆炸）
- `--deliveries-depth` 默认 2，仅扫描有限层级。
- `--limit-files` 默认 400，超过即截断并在报告标记 `truncated=true`。
- 扫描仅比对路径集合，不读取文件内容。

## 回滚方式
- 本次变更仅工具层（`prompt-dsl-system/tools/**`），无业务代码改动。
- 若需回退，恢复以下文件到上一版本即可：
  - `trace_diff.py`
  - `pipeline_runner.py`
  - `run.sh`
  - `README.md`
  - `TRACE_DIFF_TEST_NOTES.md`
  - `TRACE_DIFF_CHANGELOG.md`
