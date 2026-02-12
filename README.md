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
# optional: enforce freshness/report-head consistency directly
/usr/bin/python3 prompt-dsl-system/tools/kit_selfcheck_freshness_gate.py --report-json prompt-dsl-system/tools/kit_selfcheck_report.json --repo-root .
# optional: verify kit integrity baseline
/usr/bin/python3 prompt-dsl-system/tools/kit_integrity_guard.py verify --repo-root . --manifest prompt-dsl-system/tools/kit_integrity_manifest.json
# optional: verify pipeline trust whitelist baseline
/usr/bin/python3 prompt-dsl-system/tools/pipeline_trust_guard.py verify --repo-root . --pipeline prompt-dsl-system/04_ai_pipeline_orchestration/pipeline_kit_self_upgrade.md --whitelist prompt-dsl-system/tools/pipeline_trust_whitelist.json
# optional: enforce hmac signature on baseline files
HONGZHI_BASELINE_REQUIRE_HMAC=1 HONGZHI_BASELINE_SIGN_KEY='<secret>' /usr/bin/python3 prompt-dsl-system/tools/kit_integrity_guard.py verify --repo-root . --manifest prompt-dsl-system/tools/kit_integrity_manifest.json
# optional: enable dual-approval mode for baseline changes
HONGZHI_BASELINE_DUAL_APPROVAL=1 ./prompt-dsl-system/tools/run.sh self-upgrade -r . --strict-self-upgrade
# optional: run hmac strict smoke gate
/usr/bin/python3 prompt-dsl-system/tools/hmac_strict_smoke.py --repo-root .
# optional: run parser/contract fuzz gate
/usr/bin/python3 prompt-dsl-system/tools/fuzz_contract_pipeline_gate.py --repo-root . --iterations 400
# optional: run governance consistency guard
/usr/bin/python3 prompt-dsl-system/tools/governance_consistency_guard.py --repo-root .
# optional: run tool syntax guard
/usr/bin/python3 prompt-dsl-system/tools/tool_syntax_guard.py --repo-root .
# optional: run pipeline trust full-coverage guard
/usr/bin/python3 prompt-dsl-system/tools/pipeline_trust_coverage_guard.py --repo-root .
# optional: run baseline provenance attestation guard
/usr/bin/python3 prompt-dsl-system/tools/baseline_provenance_guard.py verify --repo-root . --provenance prompt-dsl-system/tools/baseline_provenance.json
# optional: run mutation resilience guard
/usr/bin/python3 prompt-dsl-system/tools/gate_mutation_guard.py --repo-root .
# optional: run performance budget guard
/usr/bin/python3 prompt-dsl-system/tools/performance_budget_guard.py --repo-root .
# optional: enforce performance trend regression gate
/usr/bin/python3 prompt-dsl-system/tools/performance_budget_guard.py --repo-root . --trend-enforce true
# replay machine-contract samples
bash prompt-dsl-system/tools/contract_samples/replay_contract_samples.sh --repo-root .
# optional: isolate + clean regression tmp while keeping report artifact
bash prompt-dsl-system/tools/golden_path_regression.sh \
  --repo-root . \
  --tmp-dir _regression_tmp_local \
  --report-out prompt-dsl-system/tools/regression_report.latest.md \
  --clean-tmp
# optional: execute a single shard (all|early|mid|late)
bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root . --shard-group late --clean-tmp
```

`golden_path_regression.sh` now performs signal-safe cleanup (`INT/TERM/EXIT`): it restores `skills.json` and removes injected regression skill directories on interruption.

Detailed plugin contract and governance rules: `prompt-dsl-system/tools/PLUGIN_RUNNER.md`.

CI mandatory gates are defined in `.github/workflows/kit_guardrails.yml` and enforce baseline-diff dual approval proof + hmac smoke + fuzz gate + governance consistency + tool syntax + pipeline trust coverage + baseline provenance + mutation resilience + performance budget + `validate` + `golden_path_regression` shard matrix (`early|mid|late`).
