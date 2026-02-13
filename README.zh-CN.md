# beyond-dev-ai-kit（中文版）

`prompt-dsl-system` 治理流水线与 `hongzhi-ai-kit` 插件运行器仓库。

文档导航：
- English: `README.md`
- 中文: `README.zh-CN.md`
- Agent 规则（英文）: `AGENTS.md`
- Agent 规则（中文）: `AGENTS.zh-CN.md`

## 安装（可编辑）

```bash
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -e .
```

## 入口命令

- `python3 -m hongzhi_ai_kit --help`
- `hongzhi-ai-kit --help`
- `hzkit --help`
- `hz --help`

## 自然语言路由（NL Intent）

将中英文自然语言目标路由到最合适的 pipeline：

```bash
./prompt-dsl-system/tools/run.sh intent -r . --goal "修复 ownercommittee 模块状态流转问题，最小改动"
```

当 `execution_ready=true` 且 `can_auto_execute=true` 时，可直接执行返回的 `run_command`。

已知 `module_path` 时可直接执行：

```bash
./prompt-dsl-system/tools/run.sh intent \
  -r . \
  --module-path /abs/path/to/module \
  --goal "将 Oracle SQL 迁移到 DM8，并输出回滚方案" \
  --execute
```

## Intent Router 测试

回归测试：

```bash
/usr/bin/python3 -m unittest -v prompt-dsl-system/tools/tests/intent_router/test_intent_router.py
```

压力测试（确定性、CI 友好）：

```bash
/usr/bin/python3 prompt-dsl-system/tools/tests/intent_router/intent_router_pressure.py \
  --repo-root . \
  --single-calls 6000 \
  --concurrent-calls 8000 \
  --concurrency 32 \
  --max-p99-ms 8
```

## 项目技术栈知识库扫描

```bash
/usr/bin/python3 prompt-dsl-system/tools/project_stack_scanner.py \
  --repo-root /abs/path/to/target-project \
  --project-key xywygl \
  --kit-root .
```

## 自检与验证

```bash
./prompt-dsl-system/tools/run.sh validate -r .
./prompt-dsl-system/tools/run.sh selfcheck -r .
./prompt-dsl-system/tools/run.sh self-upgrade -r . --strict-self-upgrade
```
