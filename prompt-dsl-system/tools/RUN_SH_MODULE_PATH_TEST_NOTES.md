# RUN_SH_MODULE_PATH_TEST_NOTES

## Environment
- repo: `beyond-dev-ai-kit`
- runner: `prompt-dsl-system/tools/run.sh`
- python: `/usr/bin/python3`

## Baseline self-check
- command:
```bash
./prompt-dsl-system/tools/run.sh validate --repo-root .
```
- expected: pass (`Errors=0 Warnings=0`)
- actual: pass (`Errors=0 Warnings=0`)

## Case 1: CLI module_path provided, changes inside allowed scope -> PASS
- command:
```bash
./prompt-dsl-system/tools/run.sh validate --repo-root . --module-path prompt-dsl-system
```
- expected:
  - `run.sh` prints normalized module path
  - guard passes
  - validate summary remains `Errors=0 Warnings=0`
- actual:
  - printed: `[hongzhi] module_path=/Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit/prompt-dsl-system`
  - guard: `decision=pass`
  - validate summary: `Errors=0 Warnings=0`

## Case 2: CLI module_path provided, forbidden path change detected -> FAIL-FAST (exit 2)
- note: current repo has no `.git/.svn`; to verify guard blocking logic deterministically, this case injects synthetic changed files via environment variable `HONGZHI_GUARD_CHANGED_FILES`.
- command:
```bash
HONGZHI_GUARD_CHANGED_FILES="src/main/java/com/indihx/util/Leak.java" ./prompt-dsl-system/tools/run.sh validate --repo-root . --module-path prompt-dsl-system
```
- expected:
  - hit forbidden pattern `**/util/**`
  - fail-fast and exit code 2
  - `guard_report.json` generated
- actual:
  - guard violation reported: `matched forbidden pattern: **/util/**`
  - process exit code: `2`
  - report generated: `prompt-dsl-system/tools/guard_report.json`

## Additional safety check: invalid module_path -> immediate exit 2
- command:
```bash
./prompt-dsl-system/tools/run.sh validate --repo-root . --module-path not_exist
```
- actual: `[ERROR] --module-path is not an existing directory: not_exist` and exit code `2`
