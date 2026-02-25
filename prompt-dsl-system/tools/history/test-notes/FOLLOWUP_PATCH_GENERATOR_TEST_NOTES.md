# FOLLOWUP_PATCH_GENERATOR Test Notes

Generated at: 2026-02-10 (local)

## Scope
- `followup_patch_generator.py` plan/apply behavior
- `pipeline_runner.py` + `run.sh` 子命令 `apply-followup-fixes`
- risk gate ACK gate for apply mode

## Fixture
- Working dir: `prompt-dsl-system/tools/_tmp_followup_patch`
- Input report: `followup_scan_report.json`
- Target file: `refs.md`
  - 包含一条完整旧路径（应可自动替换）
  - 包含一条 basename (`Foo.java`)（不应自动替换）

## Case 1: plan 生成 patch.diff
- Command:
```bash
./prompt-dsl-system/tools/run.sh apply-followup-fixes -r . \
  --scan-report prompt-dsl-system/tools/_tmp_followup_patch/followup_scan_report.json \
  --output-dir prompt-dsl-system/tools/_tmp_followup_patch/out
```
- Result:
  - 生成：
    - `followup_patch_plan.json`
    - `followup_patch_plan.md`
    - `followup_patch.diff`
  - `followup_patch.diff` 非空，包含 `old/path/Foo.java -> new/path/Foo.java` 的 unified diff。

## Case 2: 仅完整路径命中进入 high 替换
- Verification:
  - `followup_patch_plan.json` 中仅出现规则 `A_full_path`。
  - basename 命中 (`Foo.java`) 未进入自动替换候选。

## Case 3: apply 触发 gate（exit 4）
- Command:
```bash
./prompt-dsl-system/tools/run.sh apply-followup-fixes -r . \
  --scan-report prompt-dsl-system/tools/_tmp_followup_patch/followup_scan_report.json \
  --output-dir prompt-dsl-system/tools/_tmp_followup_patch/out \
  --mode apply --yes --dry-run false
```
- Result:
  - exit code `4`
  - 生成 token:
    - `RISK_GATE_TOKEN.txt`
    - `RISK_GATE_TOKEN.json`

## Case 4: ack-latest 通过并应用补丁
- Command:
```bash
./prompt-dsl-system/tools/run.sh apply-followup-fixes -r . \
  --scan-report prompt-dsl-system/tools/_tmp_followup_patch/followup_scan_report.json \
  --output-dir prompt-dsl-system/tools/_tmp_followup_patch/out \
  --mode apply --yes --dry-run false --ack-latest
```
- Result:
  - risk gate pass
  - 生成 `followup_patch_apply_log.md`
  - `refs.md` 变更确认：
    - 完整路径已替换为新路径
    - basename `Foo.java` 保持不变

## Case 5: apply 后复检建议
- Tool output includes:
  - `./prompt-dsl-system/tools/run.sh debug-guard -r . -m <MODULE_PATH>`
  - `./prompt-dsl-system/tools/run.sh validate -r .`

