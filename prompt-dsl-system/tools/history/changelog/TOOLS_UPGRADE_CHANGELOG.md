# TOOLS_UPGRADE_CHANGELOG

## Changed Files
- modified: `prompt-dsl-system/tools/run.sh`
- modified: `prompt-dsl-system/tools/run.zsh`
- modified: `prompt-dsl-system/tools/path_diff_guard.py`
- modified: `prompt-dsl-system/tools/pipeline_runner.py`
- modified: `prompt-dsl-system/tools/guardrails.yaml`
- modified: `prompt-dsl-system/tools/README.md`
- added: `prompt-dsl-system/tools/UPGRADE_TEST_NOTES.md`

## Behavior Changes
1. `run.sh` CLI enhanced
- added short options: `-r` == `--repo-root`, `-m` == `--module-path`
- `run` now requires module-path by default (company guardrail)
- optional bypass for `run` only:
  - `HONGZHI_ALLOW_RUN_WITHOUT_MODULE_PATH=1`
- added observability line:
  - `[hongzhi] repo_root=<...> module_path=<...|NONE> cmd=<...>`

2. Guard reliability strengthened (`path_diff_guard.py`)
- improved VCS collection for git/svn
- supports `--module-path-source` and report traceability fields
- supports `--advisory` non-block mode
- adds ignore patterns with forbidden-first precedence
- report fields enhanced:
  - `effective_rules`
  - `module_path_normalized`
  - `module_path_source`
  - `decision_reason`
  - `suggestions`

3. Runner observability strengthened (`pipeline_runner.py`)
- new command: `debug-guard`
- validate/run pass `module_path_source` to guard (`cli > pipeline > derived > none`)
- guard block message now includes:
  - guard exit code
  - primary rule
  - guard report relative path

## Rollback Plan
如果需恢复旧行为（不建议）：
1. 还原以下文件到升级前版本：
- `prompt-dsl-system/tools/run.sh`
- `prompt-dsl-system/tools/path_diff_guard.py`
- `prompt-dsl-system/tools/pipeline_runner.py`
- `prompt-dsl-system/tools/guardrails.yaml`
- `prompt-dsl-system/tools/README.md`
2. 验证：
```bash
./prompt-dsl-system/tools/run.sh validate -r .
```
3. 若需临时放宽仅 `run` 的 module-path 强制，可优先使用环境变量：
```bash
HONGZHI_ALLOW_RUN_WITHOUT_MODULE_PATH=1 ./prompt-dsl-system/tools/run.sh run -r . --pipeline <PIPELINE>
```
