# FOLLOWUP_VERIFIER_TEST_NOTES

## Environment
- repo: `beyond-dev-ai-kit`
- runner: `./prompt-dsl-system/tools/run.sh`
- verifier output: `followup_verify_report.json` + `followup_verify_report.md`

## Case 1: 制造残留并得到 WARN
1. 构造 moves 与普通文档残留：
```bash
cat > prompt-dsl-system/tools/_tmp_verify_cases/warn_case/moves.json <<'JSON'
{"mappings":[{"src":"prompt-dsl-system/tools/_tmp_verify_cases/warn_case/legacy/path/OrderSvc.java","dst":"prompt-dsl-system/tools/_tmp_verify_cases/warn_case/new/path/OrderSvc.java"}]}
JSON
cat > prompt-dsl-system/tools/_tmp_verify_cases/warn_case/README.md <<'TXT'
legacy ref: prompt-dsl-system/tools/_tmp_verify_cases/warn_case/legacy/path/OrderSvc.java
TXT
```
2. 执行验收：
```bash
./prompt-dsl-system/tools/run.sh verify-followup-fixes -r . \
  --moves prompt-dsl-system/tools/_tmp_verify_cases/warn_case/moves.json \
  --output-dir prompt-dsl-system/tools/_tmp_verify_cases/warn_case/out
```
3. 结果：`status=WARN`（`hits_total=2`）。

## Case 2: 关键目录残留并得到 FAIL
1. 在关键路径写入旧引用（`src/main/java`）：
```bash
cat > prompt-dsl-system/tools/_tmp_verify_cases/fail_case/moves.json <<'JSON'
{"mappings":[{"src":"prompt-dsl-system/tools/_tmp_verify_cases/fail_case/legacy/path/PriceSvc.java","dst":"prompt-dsl-system/tools/_tmp_verify_cases/fail_case/new/path/PriceSvc.java"}]}
JSON
cat > prompt-dsl-system/tools/_tmp_verify_cases/fail_case/src/main/java/com/acme/Test.java <<'TXT'
package com.acme;
public class Test {
  String ref = "prompt-dsl-system/tools/_tmp_verify_cases/fail_case/legacy/path/PriceSvc.java";
}
TXT
```
2. 执行验收：
```bash
./prompt-dsl-system/tools/run.sh verify-followup-fixes -r . \
  --moves prompt-dsl-system/tools/_tmp_verify_cases/fail_case/moves.json \
  --output-dir prompt-dsl-system/tools/_tmp_verify_cases/fail_case/out
```
3. 结果：`status=FAIL`（关键目录命中 + `hits_total=2`）。

## Case 3: 清除残留后得到 PASS
1. 清理测试内容（不再包含旧 token）：
```bash
cat > prompt-dsl-system/tools/_tmp_verify_cases/pass_case/moves.json <<'JSON'
{"mappings":[{"src":"prompt-dsl-system/tools/_tmp_verify_cases/pass_case/legacy/path/UserSvc.java","dst":"prompt-dsl-system/tools/_tmp_verify_cases/pass_case/new/path/UserSvc.java"}]}
JSON
cat > prompt-dsl-system/tools/_tmp_verify_cases/pass_case/README.md <<'TXT'
clean file only.
TXT
cat > prompt-dsl-system/tools/_tmp_verify_cases/pass_case/src/main/java/com/acme/Test.java <<'TXT'
package com.acme;
public class Test { String ok = "no-old-ref"; }
TXT
```
2. 执行验收（排除测试目录，避免自引用噪音）：
```bash
./prompt-dsl-system/tools/run.sh verify-followup-fixes -r . \
  --moves prompt-dsl-system/tools/_tmp_verify_cases/pass_case/moves.json \
  --output-dir prompt-dsl-system/tools/_tmp_verify_cases/pass_case/out \
  --exclude-dir _tmp_verify_cases
```
3. 结果：`status=PASS`（`hits_total=0`）。

## Status 规则确认
- `PASS`: `hits_total == 0`
- `WARN`: `0 < hits_total <= 20`
- `FAIL`: `hits_total > 20`，或命中关键目录（`src/main/java` / `pages`）且 token 属于 `exact_paths`/`fqcn_hints`
