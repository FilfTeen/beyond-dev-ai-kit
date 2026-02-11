# POLICY_PACK Test Notes

## Scope
- Repo: `/Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit`
- Only `prompt-dsl-system/tools/**` persisted.

## Case 1: tools/policy.yaml 默认生效
Command:
```bash
./prompt-dsl-system/tools/run.sh validate -r .
```
Checks:
- `Validation Summary` includes `Policy: loaded (version=1.0.0, sources=1)`
- `prompt-dsl-system/tools/policy_effective.json` generated
- `prompt-dsl-system/tools/health_report.md` window uses policy default (`20`)

Result: PASS.

## Case 2: repo override 覆盖 health.window
Temporary setup (cleaned after test):
```bash
cat > .prompt-dsl-policy.yaml <<'YAML'
health:
  window: 7
YAML
./prompt-dsl-system/tools/run.sh validate -r .
```
Check:
- `prompt-dsl-system/tools/health_report.md` => `Window: last 7 traces`

Result: PASS (`repo_override_window=7`).

## Case 3: CLI override 覆盖 repo override
Command:
```bash
./prompt-dsl-system/tools/run.sh validate -r . --policy-override health.window=9
```
Check:
- `prompt-dsl-system/tools/health_report.md` => `Window: last 9 traces`

Result: PASS (`cli_override_window=9`).

## Case 4: validate 输出 policy artifacts
Commands:
```bash
./prompt-dsl-system/tools/run.sh validate -r .
ls prompt-dsl-system/tools/policy_effective.json prompt-dsl-system/tools/policy_sources.json prompt-dsl-system/tools/policy.json
```
Check:
- Three files exist and are refreshed by validate.

Result: PASS.

## Smoke: policy.yaml 改值验证（恢复后）
Executed:
1. Temporarily changed `health.window` in `prompt-dsl-system/tools/policy.yaml` from `20` to `5`.
2. Ran `./prompt-dsl-system/tools/run.sh validate -r .`.
3. Verified `health_report.md` => `Window: last 5 traces`.
4. Restored `policy.yaml` to `window: 20` and re-ran validate.
5. Verified `health_report.md` => `Window: last 20 traces`.

Result: PASS.
