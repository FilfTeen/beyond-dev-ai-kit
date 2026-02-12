# beyond-dev-ai-kit

Repository for `prompt-dsl-system` governance pipelines and the `hongzhi-ai-kit` plugin runner package.

## Install (editable)

```bash
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -e .
```

## Entrypoints

- `python3 -m hongzhi_ai_kit --help`
- `hongzhi-ai-kit --help`
- `hzkit --help`
- `hz --help`

## Stack KB Bootstrap

Build per-project technical stack knowledge base (declared + discovered):

```bash
/usr/bin/python3 prompt-dsl-system/tools/project_stack_scanner.py \
  --repo-root /abs/path/to/target-project \
  --project-key xywygl \
  --kit-root .
```

## Kit Selfcheck

Run quality scorecard before major toolkit upgrades:

```bash
/usr/bin/python3 prompt-dsl-system/tools/kit_selfcheck.py --repo-root .
# or via wrapper
./prompt-dsl-system/tools/run.sh selfcheck -r .
# run unified self-upgrade pipeline
./prompt-dsl-system/tools/run.sh self-upgrade -r .
# strict self-upgrade preflight (recommended for major upgrades)
./prompt-dsl-system/tools/run.sh self-upgrade -r . --strict-self-upgrade
# optional: enforce selfcheck quality thresholds directly
/usr/bin/python3 prompt-dsl-system/tools/kit_selfcheck_gate.py --report-json prompt-dsl-system/tools/kit_selfcheck_report.json
# replay machine-contract samples
bash prompt-dsl-system/tools/contract_samples/replay_contract_samples.sh --repo-root .
```

Detailed plugin contract and governance rules: `prompt-dsl-system/tools/PLUGIN_RUNNER.md`.
