# prompt-dsl-system

博彦泓智科技 AI 治理 DSL 套件的核心目录。

## 目录结构

| 子目录 | 内容 | 数量 |
| --- | --- | --- |
| `00_conventions/` | 规范文件（公司章程、合规矩阵、命名规范等） | 14 |
| `04_ai_pipeline_orchestration/` | Pipeline 流水线定义 | 15 |
| `05_skill_registry/` | Skill 技能注册表 | 17 |
| `module_profiles/` | 模块画像配置 | 2 |
| `project_stacks/` | 项目技术栈知识库 | 2 |
| `tools/` | 工具链（Python/Shell） | 180+ |

## 快速入口

- **快速上手**: [QUICKSTART.md](QUICKSTART.md)
- **退出码说明**: [EXIT_CODES.md](EXIT_CODES.md)
- **多 Agent 适配**: [AGENTS_ADAPTER.md](AGENTS_ADAPTER.md)
- **公司画像**: [company_profile.yaml](company_profile.yaml)

## 核心工作流

```text
用户自然语言请求
  → intent_router (自动路由到最佳 pipeline)
  → pipeline_runner (按 YAML step 执行)
  → skill_template (领域逻辑 + 约束)
  → guard_chain (边界/循环/安全门禁)
  → artifacts (变更台账/文档/回滚方案)
```

## 版本

当前版本: **1.3.0** — 详见 [CHANGELOG.md](../CHANGELOG.md)
