# AGENTS.md

Chinese edition: `AGENTS.zh-CN.md`

## Scope

Use this repository as the execution kit for 博彦泓智科技（上海）有限公司 related development/governance tasks, especially `xx` management systems and `beyond-dev-ai-kit` evolution.
Primary authority profile: `prompt-dsl-system/00_conventions/HONGZHI_TASK_OPERATING_REQUIREMENTS.md`.
If any older skill text conflicts with this profile, follow the authority profile.

## Auto Intent Routing (Chat/NL First, Generic-First)

When the user gives a natural-language request and does not provide an explicit pipeline path:

1. Route the intent first:
   - `./prompt-dsl-system/tools/run.sh intent -r . --goal "<user_request>"`
2. Read the JSON output:
   - `selected.action_kind`: `pipeline` or `command`
   - `selected.target`: selected pipeline path or run.sh subcommand
   - `run_command`: recommended executable command
   - `execution_ready`: whether required execution parameters are resolved
   - `can_auto_execute`: execution safety decision (confidence + ambiguity gate)
3. Execute when ready:
   - If `execution_ready=true` and `can_auto_execute=true`, run `run_command`.
   - If `execution_ready=false`, ask only for `module_path`, then rerun with:
     - `./prompt-dsl-system/tools/run.sh intent -r . --module-path "<MODULE_PATH>" --goal "<user_request>" --execute`
   - If blocked by low confidence/ambiguity, ask one clarifying question; do not force execute unless user explicitly confirms.

Routing policy:
- Do not auto-select specialized pipelines by hardcoded business intent.
- Default to generic adaptive pipeline after scanning available pipelines.
- Use a specialized pipeline only when the user explicitly names that pipeline/path.

## Boundary Rules (Must Follow)

- For governance/meta pipelines, use `-m prompt-dsl-system`.
- For business-code pipelines (`sql/code/frontend/process/release`), require explicit business `module_path`.
- Never use `HONGZHI_ALLOW_RUN_WITHOUT_MODULE_PATH=1` for business-code edits.
- Forbidden-path policy remains active: `/sys`, `/error`, `/util`, `/vote`.

## Quick Commands

- Route only:
  - `./prompt-dsl-system/tools/run.sh intent -r . --goal "修复 notice 模块接口状态流转 bug"`
- Route + execute (when module path known):
  - `./prompt-dsl-system/tools/run.sh intent -r . --module-path "/abs/path/to/module" --goal "Oracle SQL 迁移到 DM8" --execute`
- Force execute only after explicit confirmation:
  - `./prompt-dsl-system/tools/run.sh intent -r . --goal "..." --execute --force-execute`
