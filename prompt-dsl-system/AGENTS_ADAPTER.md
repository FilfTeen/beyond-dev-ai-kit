# Agent Adapter / 多 Agent 适配指南

本文档说明 `beyond-dev-ai-kit` 如何在不同 AI Agent 平台上使用。

## 核心兼容性设计

套件基于 **文件系统 + shell 命令** 交互模型，不绑定特定 Agent SDK：

| 交互层 | 技术 | Agent 兼容性 |
| --- | --- | --- |
| 规范文件 | Markdown/YAML | 所有 Agent 可读 |
| Skill 定义 | YAML + prompt template | 所有 Agent 可消费 |
| Pipeline 定义 | Markdown + YAML blocks | 所有 Agent 可解析 |
| 工具执行 | Shell/Python CLI | 需 `run_command` 能力 |
| 机器信号 | stdout 行 (`HONGZHI_*`) | 需 stdout 解析能力 |

## 各平台适配建议

### Codex (原生平台)

- **兼容性**: 100%，原生支持
- **入口**: `AGENTS.md` → 自动加载执行规则
- **工具**: `run_command` 直接执行所有 shell 命令
- **信号**: stdout 自动捕获 `HONGZHI_*` 行

### Gemini (Antigravity)

- **兼容性**: 95%
- **入口**: 读取 `AGENTS.md` 作为系统上下文
- **工具**: `run_command` 工具可执行 shell 命令
- **注意事项**:
  - Gemini 不自动加载 `AGENTS.md`，需在对话开始时显式引用
  - 建议在首条消息中包含：`请先阅读 AGENTS.md 了解执行规则`
  - `run_command` 需用户批准，可通过 `SafeToAutoRun: true` 标记安全命令

### Claude / Cursor

- **兼容性**: 90%
- **入口**: 通过 `.cursorrules` 或系统 prompt 引用 `AGENTS.md`
- **工具**: 需确认 run_command 或 terminal 工具可用
- **注意事项**:
  - 需手动将 `AGENTS.md` 内容作为上下文注入
  - 长对话中上下文窗口有限，建议使用 `QUICKSTART.md` 简化

### ChatGPT / Custom GPT

- **兼容性**: 70%
- **限制**:
  - 无文件系统访问（除非通过 Code Interpreter）
  - 无 `run_command` 能力
  - 适用于：规范查阅、prompt 模板参考、skill 设计
- **适配方式**:
  - 将 skill YAML 内容直接粘贴到对话中
  - 手动执行 shell 命令并将输出反馈到对话

## Skill YAML 跨平台使用

所有 skill 的 `prompt_template` 字段采用 Mustache 模板（`{{variable}}`），可在任何平台上手动替换变量后使用：

```yaml
# 从 skill YAML 提取 prompt_template
# 替换 {{module_path}} 等变量
# 直接作为 prompt 发送给任何 Agent
```

## Pipeline 手动执行

不支持 `run.sh` 的平台可手动执行 pipeline：

1. 阅读 pipeline Markdown 文件
2. 按 Step 顺序执行
3. 每一步使用对应 skill 的 prompt_template
4. 手动传递 `input_artifact_refs`

## 建议的 .cursorrules 引用

```text
# .cursorrules (用于 Cursor)
Always read and follow the rules in AGENTS.md before starting any task.
Reference prompt-dsl-system/00_conventions/HONGZHI_TASK_OPERATING_REQUIREMENTS.md for execution standards.
```
