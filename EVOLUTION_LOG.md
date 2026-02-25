# Evolution Log — beyond-dev-ai-kit (2026-02-25)

> 本文档记录 beyond-dev-ai-kit 的演进历史、当前基线和未来方向，供后续 Agent（Codex 等）和开发者参阅。
> 说明：文档中 `V1.2.0` 相关段落均为历史快照；当前有效基线请以“九、V1.3.0 当前基线（有效）”为准。

## 一、会话目标

将 `beyond-dev-ai-kit` 打造为**完全体**——一个作用域在"博彦泓智科技（上海）有限公司"下、agent 在对话/作业中能**自动发现、零配置使用**的插件级通用 prompt/DSL/skill/pipeline 套件。

## 二、已完成变更（V1.1.0 → V1.2.0）

### 2.1 Agent 平台自动注入（T1）

| 文件 | 目标平台 | 作用 |
| --- | --- | --- |
| `.cursorrules` | Cursor IDE | 打开仓库即自动加载执行规则 |
| `.github/copilot-instructions.md` | GitHub Copilot | 自动注入项目上下文 |
| `.windsurfrules` | Windsurf IDE | 打开仓库即自动加载执行规则 |
| `AGENTS.md` (已有) | Codex | 原生支持 |

所有注入文件统一引用 `AGENTS.md` 作为权威源，形成**一次维护、多平台生效**的扇出结构。

### 2.2 公司域身份（T2）

- `prompt-dsl-system/company_profile.yaml`: `name` 更新为 `"博彦泓智科技（上海）有限公司"`，新增 `name_en` 和 `business` 字段。

### 2.3 Skill/Pipeline 完全覆盖（T3）

**5 个新增 Skill**（12→17）:

| Skill | 领域 | 文件 |
| --- | --- | --- |
| `skill_test_gen` | test | `skills/test/skill_test_gen.yaml` |
| `skill_security_audit` | security | `skills/security/skill_security_audit.yaml` |
| `skill_api_design_review` | code | `skills/code/skill_api_design_review.yaml` |
| `skill_performance_analysis` | code | `skills/code/skill_performance_analysis.yaml` |
| `skill_docs_i18n` | docs | `skills/docs/skill_docs_i18n.yaml` |

**2 个新增 Pipeline**（13→15）:

| Pipeline | 文件 |
| --- | --- |
| `pipeline_test_gen.md` | 扫描→生成→验证 3 步测试流水线 |
| `pipeline_security_audit.md` | SQL 注入→认证 XSS→综合报告 3 步安全审计流水线 |

所有新 skill 已在 `skills.json` 注册（status: `deployed`，已在 V1.2.0 → V1.3.0 迭代中完成 promotion）。

### 2.4 V1.1.0 补丁级改进（在版本升级前已完成）

| 类别 | 变更 |
| --- | --- |
| 基础设施 | `.gitignore` 增强、`LICENSE` (MIT)、`baseline_rebuild_all.sh` |
| 代码质量 | 17 个函数 docstring（`pipeline_yaml_parser.py` ×12、`pipeline_profile_injector.py` ×5） |
| 死代码清理 | 移除 `bool_hint` (health_runbook_generator.py)、`compute_cache_hit_rate` (hongzhi_plugin.py) |
| 版本统一 | `PLUGIN_VERSION` 从 `__init__.py` 导入，消除硬编码 |
| 单元测试 | 83 个 unittest (yaml_parser ×48、profile_injector ×16、snapshot ×19) |
| 开发体验 | `CHANGELOG.md`、`Makefile` (validate/test/selfcheck/baseline-rebuild/clean) |
| 回归修复 | Phase40 fixture 补 `agent_active_ops` 维度、基线构建顺序 (trust→provenance→manifest) |

### 2.5 版本升级（T4）

- `pyproject.toml`: 1.1.0 → 1.2.0
- `hongzhi_ai_kit/__init__.py`: 1.1.0 → 1.2.0
- `hongzhi_plugin.py`: CONTRACT_VERSION + PLUGIN_VERSION → 1.2.0

### 2.6 文档更新（T5）

- `CHANGELOG.md`: 新增 v1.2.0 条目
- `README.md`: 架构图更新 (17 skills, 15 pipelines)
- `QUICKSTART.md`: 目录结构计数更新
- `prompt-dsl-system/README.md`: **新建** 子目录导航文档

## 三、验证状态（V1.2.0 历史快照）

| 维度 | 结果 |
| --- | --- |
| 编译检查 | ✅ 所有修改文件通过 `py_compile` |
| 单元测试 | ✅ 83/83 (0.010s) |
| 基线一致性 | ✅ integrity 50/50, provenance 5/5, trust 15/15 |
| 金标回归 | ✅ 169/169 |

## 四、当前架构快照

```
beyond-dev-ai-kit/ (v1.3.0)
├── AGENTS.md                    # Codex 自动加载
├── .cursorrules                 # Cursor 自动加载
├── .windsurfrules               # Windsurf 自动加载
├── .github/copilot-instructions.md  # Copilot 自动加载
├── CHANGELOG.md / LICENSE / Makefile / .gitignore
├── pyproject.toml               # 包配置 (v1.3.0)
└── prompt-dsl-system/
    ├── README.md                # 子目录导航
    ├── QUICKSTART.md / EXIT_CODES.md / AGENTS_ADAPTER.md
    ├── company_profile.yaml     # 公司画像
    ├── 00_conventions/          # 14 个规范文件
    ├── 04_ai_pipeline_orchestration/  # 15 个 pipeline
    ├── 05_skill_registry/       # 17 个 skill (skills.json)
    ├── module_profiles/         # 模块画像
    ├── project_stacks/          # 项目技术栈 KB
    └── tools/                   # 180+ 工具脚本
        ├── hongzhi_plugin.py    # 核心插件 (4900+ 行)
        ├── pipeline_runner.py   # Pipeline 执行器
        ├── pipeline_yaml_parser.py      # YAML 解析（已提取）
        ├── pipeline_profile_injector.py # 画像注入（已提取）
        ├── hongzhi_ai_kit/      # 包模块
        │   ├── __init__.py      # v1.3.0
        │   ├── snapshot.py      # 快照模块（已提取）
        │   └── cli.py           # CLI 入口
        ├── tests/               # 100 个 unittest
        └── golden_path_regression.sh  # 172 项回归
```

## 五、未来改进方向

以下方向按优先级排列，供后续 Agent 参考决策：

### P0 — 高优先级

1. ~~**新 Skill 从 staging 升级到 deployed**~~: ✅ 已完成，全部 17 个 skill 均为 `deployed`。
2. **Intent Router 关键词扩展**: `intent_router.py` 可能需要新增关键词映射，使其能正确路由"测试生成"、"安全审计"等意图到新 pipeline。验证方式: `run.sh intent -r . --goal "为 notice 模块生成单元测试"` 应路由到 `pipeline_test_gen.md`。
3. **Golden Regression 新增覆盖**: 为 2 个新 pipeline 和 5 个新 skill 添加回归测试 phase，确保 skill YAML 解析正确、pipeline step 提取正常。

### P1 — 中优先级

1. ~~**FACT_BASELINE.md 更新**~~: ✅ 已确认 Skill 清单=17、Pipeline 清单=15，计数正确。
2. **COMPLIANCE_MATRIX.md 更新**: 检查是否需要新增 test/security 相关合规项。
3. **README.zh-CN.md 同步**: 中文版 README 的架构图计数需同步到 17/15。
4. **AGENTS.zh-CN.md 同步**: 中文版 AGENTS 如有计数引用也需同步。
5. **Makefile 补充**: 可添加 `make lint` (skill YAML 格式校验)、`make audit` (安全审计) 目标。

### P2 — 低优先级

1. **MCP Server 封装**: 将 skill/pipeline 暴露为 MCP tools，实现跨 Agent 零配置调用（高价值、中等工作量）。
2. **VS Code 扩展**: 侧边栏浏览 skill/pipeline/convention，提供 IntelliSense 支持。
3. **Selfcheck 维度扩展**: 当前 8 维度可考虑增加 `test_coverage` 和 `security_posture` 维度。
4. **Skill 热加载**: 支持运行时注册新 skill 无需重启。

### P3 — 质量保障

1. **单元测试扩展**: 当前 100 个测试覆盖多个模块，可扩展到 `hongzhi_plugin.py`、`pipeline_runner.py`、`ops_guard.py`、`health_runbook_generator.py`。
2. **E2E 测试**: 新 pipeline（test_gen/security_audit）的端到端执行测试。
3. **性能基准**: 对 intent router 和 pipeline runner 建立性能回归基线。

## 六、关键约束提醒

1. **Kit 只允许 stdlib**: 所有 Python 工具必须零外部依赖（`prompt-dsl-system/tools/` 下所有 `.py`）。
2. **Contract 兼容**: CONTRACT_VERSION 变更需确保 `contract_schema_v2.json` 兼容旧版本输出。
3. **基线构建顺序**: trust → provenance → manifest（使用 `baseline_rebuild_all.sh`）。
4. **Forbidden paths**: `/sys`, `/error`, `/util`, `/vote` — 所有 skill 和 pipeline 必须在 boundary_policy 中声明。
5. **Skill 注册**: 新 skill 必须同时更新 `skills.json` 和创建 YAML 文件到对应 domain 子目录。
6. **Validate 模块门禁**: 根目录文件（`.gitignore`, `LICENSE`, `Makefile`, `.cursorrules` 等）不属于 `prompt-dsl-system/` 模块边界，validate 会正确拦截，这是预期行为。

## 七、快速验证命令

```bash
# 编译检查
python3 -m py_compile prompt-dsl-system/tools/hongzhi_plugin.py

# 单元测试 (100 个)
python3 -m unittest discover -s prompt-dsl-system/tools/tests -v

# 基线重建 + 自验证
bash prompt-dsl-system/tools/baseline_rebuild_all.sh --repo-root .

# 金标回归 (172 项)
bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root . --clean-tmp

# Intent 路由测试
./prompt-dsl-system/tools/run.sh intent -r . --goal "为模块生成单元测试"

# 或使用 Makefile
make test        # validate + unit tests
make baseline-rebuild  # 基线重建
```

## 八、Post-V1.2.0 增量修复（2026-02-25）

> 说明：本节为后续 Agent 增量修复记录；上文中的 `83/83`、`169/169` 属于历史快照，不再作为当前基线结论。

### 8.1 已落地改进

1. `run.sh validate` 后置门禁新增并接入 health 汇总：
   - `docs_facts_guard.py`
   - `deployed_skill_ref_guard.py`
2. 新增门禁开关（默认阻断）：
   - `HONGZHI_DOCS_FACTS_GUARD_ENFORCE=1|0`
   - `HONGZHI_DEPLOYED_SKILL_REF_ENFORCE=1|0`
3. `Makefile` 增强：
   - 新增 `doctor`（`baseline-rebuild -> promotion-matrix-strict -> validate -> selfcheck`）
   - 新增 `promotion-matrix-strict`、`docs-facts`、`deployed-ref`
4. CI 增强：
   - `.github/workflows/kit_guardrails.yml` 在核心门禁前新增 `baseline_rebuild_all.sh` 预步骤。
5. Skill 覆盖关系显式化：
   - `skills.json` 支持并落地 `covers[]`（示例：`skill_governance_plugin_discover_with_hints` 覆盖 `skill_governance_plugin_discover`）。
   - `deployed_skill_ref_guard.py` 优先读取 `covers[]` 做引用覆盖判定（保留 `_with_hints` 兼容推断）。
   - `SKILL_SPEC.md` 已补充 `covers[]` 约定说明。
6. CI 门禁显式化：
   - `.github/workflows/kit_guardrails.yml` 新增独立步骤 `Docs Facts Guard` 与 `Deployed Skill Reference Guard`（不再只依赖 validate 间接触发）。
7. 发布流程增强：
   - `Makefile` 新增 `release-check` 目标（baseline + promotion-matrix-strict + docs/deployed-ref + repo-wide validate + selfcheck + golden）。

### 8.2 当前验证快照（覆盖旧统计）

- 单元测试：`97/97 PASS`
- 金标回归：`172/172 PASS`
- `run.sh validate -r . -m .`：`PASS`
- `skill_promotion_matrix --fail-on-pending`：`pending=0`

## 九、V1.3.0 当前基线（有效）

### 9.1 本轮迭代落地

1. 运行产物去版本化：
   - `prompt-dsl-system/tools` 下 37 个 runtime 输出从 git index 移除并由 `.gitignore` 接管。
2. 历史文档归档：
   - `tools` 根目录 `*_CHANGELOG.md`、`*_TEST_NOTES.md` 迁移到 `tools/history/`。
   - `artifacts` 仅保留 `R27-R29` + 当前无轮次稿；`R16-R26` 清理完成。
   - 静态 `run_plan_*.yaml` 迁移到 `tools/history/run-plans/`。
3. 新增门禁：
   - `runtime_outputs_tracking_guard.py`（validate / release-check / CI 已接入）
   - `double_run_consistency_guard.py`（release-check / CI 已接入）
4. 兼容与文档：
   - `ops_guard.py` 候选日志源改为“history 优先、旧路径回退”。
   - `README.md`、`README.zh-CN.md`、`prompt-dsl-system/tools/README.md` 增补 runtime 输出策略。
5. 版本：
   - `pyproject.toml`、`hongzhi_ai_kit/__init__.py`、`hongzhi_plugin.py` 升级为 `1.3.0`。
   - `CONTRACT_VERSION` 同步升级 `1.3.0`（保持 additive 兼容策略）。

### 9.2 验证口径

- 本节统计以本轮 `baseline_rebuild + 全链路回归` 的最终结果为准。
- 单元测试：`100/100 PASS`
- `runtime_outputs_tracking_guard`：`PASS (tracked_runtime_outputs=0)`
- `run.sh validate -r . -m .`：`PASS`
- `run.sh selfcheck -r .`：`PASS (overall_score=1.0, level=high)`
- `run.sh self-upgrade -r . --strict-self-upgrade`：`PASS`
- `golden_path_regression`：`172/172 PASS`
- `double_run_consistency_guard`：`PASS (tracked_diff_is_stable=1)`
- `make release-check`：`PASS`
