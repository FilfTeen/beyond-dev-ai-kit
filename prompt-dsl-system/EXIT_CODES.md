# Exit Codes Reference / 退出码参考

本文档列出 `hongzhi_plugin.py` 及核心治理门禁使用的所有退出码。

## Plugin Runner Exit Codes

| 退出码 | 名称 | 说明 |
| --- | --- | --- |
| `0` | SUCCESS | 正常完成 |
| `1` | GENERAL_ERROR | 通用错误（参数、运行时异常等） |
| `2` | CONTRACT_VIOLATION | 合约校验失败（CONTRACT_OK=0） |
| `3` | MUTATION_DETECTED | 快照差异检测到目标仓库被修改（read-only 策略违反） |
| `10` | GOVERNANCE_DISABLED | 治理策略禁用，拒绝执行 |
| `11` | GOVERNANCE_DENIED | 治理策略显式拒绝此操作 |
| `12` | GOVERNANCE_TOKEN_INVALID | 治理 Token 无效/过期/scope 不匹配 |
| `13` | POLICY_PARSE_ERROR | policy.yaml 解析失败（fail-closed） |
| `20` | LIMITS_STRICT | 严格模式下超出限制阈值 |
| `21` | NEEDS_HUMAN_HINT | 低置信度需要人工提示（strict 模式） |
| `22` | HINT_EXPIRED | 应用的 hints 已过期 |
| `23` | HINT_SCOPE_BLOCKED | permit-token scope 缺少 hint_bundle |
| `24` | INDEX_SCOPE_BLOCKED | permit-token scope 缺少 federated_index |
| `25` | SCAN_GRAPH_MISMATCH | scan graph 一致性校验失败 |
| `26` | COMPANY_SCOPE_MISMATCH | 公司域 scope 不匹配 |

## Governance Gate Exit Codes

| 退出码 | 门禁 | 说明 |
| --- | --- | --- |
| `0` | All | 通过 |
| `1` | All | 运行时错误 |
| `非0` | `kit_selfcheck_gate.py` | 质量分/维度/新鲜度不达标 |
| `非0` | `kit_integrity_guard.py` | 完整性哈希不匹配 |
| `非0` | `pipeline_trust_guard.py` | Pipeline 信任白名单校验失败 |
| `非0` | `baseline_provenance_guard.py` | 基线溯源校验失败 |
| `非0` | `gate_mutation_guard.py` | 变异抗性测试未通过 |
| `非0` | `performance_budget_guard.py` | 性能预算超标 |

## Machine-Readable Output Lines

| 信号 | 格式 | 说明 |
| --- | --- | --- |
| `HONGZHI_CAPS` | `HONGZHI_CAPS <path> json='{...}'` | 能力扫描结果路径 |
| `HONGZHI_HINTS` | `HONGZHI_HINTS <path> json='{...}'` | 人工提示建议路径 |
| `HONGZHI_INDEX` | `HONGZHI_INDEX <path> json='{...}'` | 联邦索引更新路径 |
| `HONGZHI_STATUS` | `HONGZHI_STATUS ...` | 插件状态信息 |
| `HONGZHI_GOV_BLOCK` | `HONGZHI_GOV_BLOCK reason=... code=...` | 治理拦截信号 |
| `HONGZHI_HINTS_BLOCK` | `HONGZHI_HINTS_BLOCK ...` | Hint scope 拦截信号 |
| `HONGZHI_INDEX_BLOCK` | `HONGZHI_INDEX_BLOCK ...` | Index scope 拦截信号 |
| `KIT_CAPS` | `KIT_CAPS <path> ...` | Kit 自检能力信号 |

## validate / selfcheck Exit Codes

| 退出码 | 说明 |
| --- | --- |
| `0` | 全部通过 |
| `1` | 至少一个核心检查失败 |

## golden_path_regression.sh Exit Codes

| 退出码 | 说明 |
| --- | --- |
| `0` | 所有 Phase 测试通过 |
| `1` | 至少一个 Phase 测试失败 |
