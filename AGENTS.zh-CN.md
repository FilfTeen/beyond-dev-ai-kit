# AGENTS.zh-CN.md

## 适用范围

本仓库作为博彦泓智科技（上海）有限公司相关开发/治理任务的执行套件，重点覆盖 `xx` 管理系统与 `beyond-dev-ai-kit` 迭代。
最高权威规范：`prompt-dsl-system/00_conventions/HONGZHI_TASK_OPERATING_REQUIREMENTS.md`。
若旧 skill 文本与该规范冲突，以权威规范为准。

## 自动意图路由（聊天/自然语言优先，通用优先）

当用户只给自然语言目标、未指定 pipeline 路径时：

1. 先做意图路由：
   - `./prompt-dsl-system/tools/run.sh intent -r . --goal "<user_request>"`
2. 读取 JSON 输出字段：
   - `selected.action_kind`: `pipeline` 或 `command`
   - `selected.target`: 选中 pipeline 路径或 run.sh 子命令
   - `run_command`: 推荐执行命令
   - `execution_ready`: 执行参数是否齐全
   - `can_auto_execute`: 是否满足自动执行门槛（置信度 + 歧义闸门）
3. 条件满足即执行：
   - 若 `execution_ready=true` 且 `can_auto_execute=true`，执行 `run_command`
   - 若 `execution_ready=false`，仅补问 `module_path`，然后重跑：
     - `./prompt-dsl-system/tools/run.sh intent -r . --module-path "<MODULE_PATH>" --goal "<user_request>" --execute`
   - 若被低置信度/高歧义阻断，仅提出一个澄清问题；未经用户明确确认，不强制执行

路由策略：
- 禁止基于硬编码业务意图自动挑选“专用 pipeline”。
- 默认先扫描可用 pipeline，再回退到通用自适应 pipeline。
- 仅当用户明确指定 pipeline/路径时才使用专用 pipeline。

## 边界规则（必须遵守）

- 治理/元信息 pipeline：使用 `-m prompt-dsl-system`
- 业务代码 pipeline（`sql/code/frontend/process/release`）：必须提供明确业务 `module_path`
- 禁止在业务代码改动中使用 `HONGZHI_ALLOW_RUN_WITHOUT_MODULE_PATH=1`
- 禁止路径规则持续生效：`/sys`、`/error`、`/util`、`/vote`

## 常用命令

- 仅路由：
  - `./prompt-dsl-system/tools/run.sh intent -r . --goal "修复 notice 模块接口状态流转 bug"`
- 路由并执行（已知 module path）：
  - `./prompt-dsl-system/tools/run.sh intent -r . --module-path "/abs/path/to/module" --goal "Oracle SQL 迁移到 DM8" --execute`
- 强制执行（仅在用户明确确认后）：
  - `./prompt-dsl-system/tools/run.sh intent -r . --goal "..." --execute --force-execute`
