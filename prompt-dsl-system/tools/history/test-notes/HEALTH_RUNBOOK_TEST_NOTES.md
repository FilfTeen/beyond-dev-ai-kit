# HEALTH_RUNBOOK_TEST_NOTES

## Scope
- Repo: `beyond-dev-ai-kit`
- Date: 2026-02-10
- Toolchain: `/usr/bin/python3`, `./prompt-dsl-system/tools/run.sh`

## Case 1: validate 后自动生成 runbook

### Command
```bash
./prompt-dsl-system/tools/run.sh validate -r . --runbook-mode safe
```

### Expected
- 生成：
  - `prompt-dsl-system/tools/health_runbook.md`
  - `prompt-dsl-system/tools/health_runbook.sh`
  - `prompt-dsl-system/tools/health_runbook.json`
- stdout 包含 runbook 路径。

### Actual
- 生成成功。
- stdout 包含：
  - `Health runbook generated: prompt-dsl-system/tools/health_runbook.md`
  - `[hongzhi] health_runbook=prompt-dsl-system/tools/health_runbook.md`

---

## Case 2: placeholders 未填时 .sh 阻断（exit 2）

### Command
```bash
./prompt-dsl-system/tools/health_runbook.sh
```

### Expected
- 因 `MODULE_PATH` 未设置而退出，exit code=2。

### Actual
- 输出：`[ERROR] MODULE_PATH is required. Export MODULE_PATH first.`
- `EXIT_CODE=2`。

---

## Case 3: safe 模式不包含 apply/ack 命令

### Check
```bash
/usr/bin/python3 - <<'PY'
import json
obj=json.load(open('prompt-dsl-system/tools/health_runbook.json','r',encoding='utf-8'))
cmds=[s.get('command') for s in obj.get('steps',[]) if isinstance(s,dict) and isinstance(s.get('command'),str)]
print('has_apply=',any('--mode apply' in c for c in cmds))
print('has_ack=',any(' --ack' in c or '--ack-latest' in c for c in cmds))
PY
```

### Expected
- `has_apply=False`
- `has_ack=False`

### Actual
- `has_apply=False`
- `has_ack=False`

