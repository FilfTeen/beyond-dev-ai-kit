# Quick Start / 快速上手

> 5 分钟从零到运行 beyond-dev-ai-kit

## 1. 安装

```bash
cd beyond-dev-ai-kit
python3 -m pip install -e .
```

安装后可用命令：`hongzhi-ai-kit` / `hzkit` / `hz`

## 2. 验证安装

```bash
hz --help
./prompt-dsl-system/tools/run.sh validate -r .
```

输出 `Errors=0 Warnings=0` 表示套件就绪。

## 3. 自然语言路由（推荐入口）

直接描述你的目标，套件自动选择最佳 pipeline：

```bash
./prompt-dsl-system/tools/run.sh intent -r . \
  --goal "修复 notice 模块接口状态流转 bug"
```

观察输出中的 `selected.target` 和 `run_command`，确认后执行。

## 4. 指定模块执行

```bash
./prompt-dsl-system/tools/run.sh intent -r . \
  --module-path /path/to/module \
  --goal "Oracle SQL 迁移到 DM8" \
  --execute
```

## 5. Kit 自升级

```bash
./prompt-dsl-system/tools/run.sh intent -r . \
  --module-path prompt-dsl-system \
  --goal "升级 prompt/DSL/skill/pipeline 套件" \
  --execute
```

## 6. 质量自检

```bash
./prompt-dsl-system/tools/run.sh selfcheck -r .
```

## 7. 回归测试

```bash
bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root . --clean-tmp
```

## 常用命令速查

| 命令 | 用途 |
| --- | --- |
| `run.sh intent -r . --goal "..."` | 自然语言路由 |
| `run.sh validate -r .` | 核心验证 |
| `run.sh selfcheck -r .` | 质量自检 |
| `run.sh self-upgrade -r .` | 统一自升级 |
| `run.sh self-upgrade -r . --strict-self-upgrade` | 严格自升级 |
| `run.sh agent-audit -r .` | Agent 能力审计 |
| `run.sh list` | 列出可用 pipelines |
| `run.sh run -r . -p <pipeline> -m <module>` | 执行指定 pipeline |
| `golden_path_regression.sh --repo-root .` | 回归测试 |

## 目录结构

```text
beyond-dev-ai-kit/
├── AGENTS.md              # Agent 执行规则
├── README.md              # 完整文档
├── pyproject.toml          # 包配置
└── prompt-dsl-system/
    ├── 00_conventions/     # 规范文件（14 个）
    ├── 04_ai_pipeline_orchestration/  # Pipeline（15 个）
    ├── 05_skill_registry/  # Skill 注册表（17 个）
    └── tools/              # 工具链（180+ 个）
```

## 下一步

- 查看 [README.md](../README.md) 了解完整功能
- 查看 [AGENTS.md](../AGENTS.md) 了解 Agent 执行规则
- 查看 [EXIT_CODES.md](EXIT_CODES.md) 了解退出码含义
