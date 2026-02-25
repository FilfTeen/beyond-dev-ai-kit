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

## 运行产物策略

- `prompt-dsl-system/tools` 下的运行产物默认是生成文件，**不作为版本化资产提交**。
- 典型文件：`run_plan.yaml`、`validate_report.json`、`health_report.*`、`trace_index.*`、`guard_report.json`、`followup_*`。
- 历史文档与静态快照统一归档到 `prompt-dsl-system/tools/history/**`。

## 自然语言路由（NL Intent）

将中英文自然语言目标路由到最合适的 pipeline：

```bash
./prompt-dsl-system/tools/run.sh intent -r . --goal "修复 ownercommittee 模块状态流转问题，最小改动"
```

`intent` 同时支持 pipeline 路由和命令路由（`validate`/`selfcheck`/`self-upgrade`/`agent-audit`/`list`），返回字段：

- `selected.action_kind`
- `selected.target`
- `selected.default_module_path`（仅治理类 pipeline）
- `module_path_source` (`cli|goal|selected_default|missing`)
- `can_auto_execute`
- `routing_time_ms`

路由策略（通用优先 + kit 自升级例外）：

- 路由器扫描可用 pipeline，报告候选列表。
- 默认回退到通用自适应 pipeline。
- 当目标明确为 `beyond-dev-ai-kit` 的 `prompt/DSL/skill/pipeline` 套件升级时，优先路由到 `pipeline_kit_self_upgrade.md`。
- 显式指定 pipeline 的优先级高于命令关键字匹配。
- 业务 pipeline 不自动填充 `-m`；治理类 pipeline 可默认为 `prompt-dsl-system`。

已知 `module_path` 时可直接执行：

```bash
./prompt-dsl-system/tools/run.sh intent \
  -r . \
  --module-path /abs/path/to/module \
  --goal "将 Oracle SQL 迁移到 DM8，并输出回滚方案" \
  --execute

# kit 自升级路由
./prompt-dsl-system/tools/run.sh intent \
  -r . \
  --module-path prompt-dsl-system \
  --goal "改进 beyond-dev-ai-kit 的 prompt/DSL/skill/pipeline 套件并落地" \
  --execute
```

低置信度或歧义阻断时，先澄清目标或显式覆盖：

```bash
./prompt-dsl-system/tools/run.sh intent -r . --goal "..." --execute --force-execute
```

Intent Router 压力测试（确定性、CI 友好）：

```bash
/usr/bin/python3 prompt-dsl-system/tools/tests/intent_router/intent_router_pressure.py --repo-root . --single-calls 6000 --concurrent-calls 8000 --concurrency 32
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
# 核心验证
./prompt-dsl-system/tools/run.sh validate -r .
# 质量自检
./prompt-dsl-system/tools/run.sh selfcheck -r .
# 统一自升级
./prompt-dsl-system/tools/run.sh self-upgrade -r .
# 严格自升级（推荐用于重大升级前）
./prompt-dsl-system/tools/run.sh self-upgrade -r . --strict-self-upgrade
# Agent 能力审计
./prompt-dsl-system/tools/run.sh agent-audit -r . --single-calls 12000 --concurrent-calls 16000 --concurrency 48 --max-p99-ms 12
# selfcheck 质量阈值门禁
/usr/bin/python3 prompt-dsl-system/tools/kit_selfcheck_gate.py --report-json prompt-dsl-system/tools/kit_selfcheck_report.json
# selfcheck 新鲜度门禁
/usr/bin/python3 prompt-dsl-system/tools/kit_selfcheck_freshness_gate.py --report-json prompt-dsl-system/tools/kit_selfcheck_report.json --repo-root .
# kit 完整性门禁
/usr/bin/python3 prompt-dsl-system/tools/kit_integrity_guard.py verify --repo-root . --manifest prompt-dsl-system/tools/kit_integrity_manifest.json
# pipeline 信任白名单门禁
/usr/bin/python3 prompt-dsl-system/tools/pipeline_trust_guard.py verify --repo-root . --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md --whitelist prompt-dsl-system/tools/pipeline_trust_whitelist.json
# HMAC 严格烟测
/usr/bin/python3 prompt-dsl-system/tools/hmac_strict_smoke.py --repo-root .
# parser/contract fuzz 门禁
/usr/bin/python3 prompt-dsl-system/tools/fuzz_contract_pipeline_gate.py --repo-root . --iterations 400
# 治理一致性门禁
/usr/bin/python3 prompt-dsl-system/tools/governance_consistency_guard.py --repo-root .
# 工具语法门禁
/usr/bin/python3 prompt-dsl-system/tools/tool_syntax_guard.py --repo-root .
# pipeline 信任全覆盖门禁
/usr/bin/python3 prompt-dsl-system/tools/pipeline_trust_coverage_guard.py --repo-root .
# 基线溯源门禁
/usr/bin/python3 prompt-dsl-system/tools/baseline_provenance_guard.py verify --repo-root . --provenance prompt-dsl-system/tools/baseline_provenance.json
# 变异抗性门禁
/usr/bin/python3 prompt-dsl-system/tools/gate_mutation_guard.py --repo-root .
# 性能预算门禁
/usr/bin/python3 prompt-dsl-system/tools/performance_budget_guard.py --repo-root .
# 性能趋势回归门禁
/usr/bin/python3 prompt-dsl-system/tools/performance_budget_guard.py --repo-root . --trend-enforce true
# 文档事实门禁（README/FACT 关键计数一致性）
/usr/bin/python3 prompt-dsl-system/tools/docs_facts_guard.py --repo-root .
# deployed skill 引用覆盖门禁
/usr/bin/python3 prompt-dsl-system/tools/deployed_skill_ref_guard.py --repo-root .
# 运行产物去版本化门禁
/usr/bin/python3 prompt-dsl-system/tools/runtime_outputs_tracking_guard.py --repo-root .
# 双跑一致性门禁（validate/selfcheck 连跑不新增 tracked diff）
/usr/bin/python3 prompt-dsl-system/tools/double_run_consistency_guard.py --repo-root .
# 合约样例回放
bash prompt-dsl-system/tools/contract_samples/replay_contract_samples.sh --repo-root .
# 黄金回归测试（支持分片）
bash prompt-dsl-system/tools/golden_path_regression.sh \
  --repo-root . \
  --tmp-dir _regression_tmp_local \
  --report-out prompt-dsl-system/tools/regression_report.latest.md \
  --clean-tmp
# 单独分片执行（all|early|mid|late）
bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root . --shard-group late --clean-tmp
# 一键发布就绪检查
make release-check
```

`golden_path_regression.sh` 支持信号安全清理（`INT/TERM/EXIT`）：中断时自动恢复 `skills.json` 并移除注入的回归 skill 目录。

详细插件合约与治理规则：`prompt-dsl-system/tools/PLUGIN_RUNNER.md`。

CI 必过门禁定义在 `.github/workflows/kit_guardrails.yml` 中，强制执行 baseline 重建 + baseline-diff 双审批 + hmac 烟测 + fuzz 门禁 + 治理一致性 + 工具语法 + pipeline 信任全覆盖 + 基线溯源 + 变异抗性 + 性能预算 + 文档事实门禁 + deployed skill 引用门禁 + 运行产物跟踪门禁 + `validate` + 双跑一致性门禁 + `golden_path_regression` 分片矩阵（`early|mid|late`）。CI 上传各分片报告、合并摘要，当分片汇总契约破坏（报告缺失 / 非通过分片 / 计数不匹配）时硬失败。
