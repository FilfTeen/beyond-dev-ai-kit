# A2 R17 Change Ledger

## Functional Changes

1. Added standard packaging via root `pyproject.toml`.
2. Added console entries: `hongzhi-ai-kit`, `hzkit`, `hz`.
3. Updated module loader in `hongzhi_ai_kit/cli.py` to support installed-first import and source fallback.
4. Upgraded runner to contract v4-compatible outputs:
   - stdout `HONGZHI_CAPS <abs_path>`
   - stdout governance block line: `HONGZHI_GOV_BLOCK ...`
   - workspace append-only `capabilities.jsonl`
5. Preserved v3 summary line for backward compatibility.
6. Added governance/plugin integration assets:
   - `skill_governance_plugin_runner.yaml`
   - `pipeline_plugin_discover.md`
7. Added Phase23 (4 checks) to regression.

## Docs/Baseline Updates

- `PLUGIN_RUNNER.md`: install + v4 contract sections
- `FACT_BASELINE.md`: skills/pipelines/tools/regression baseline refresh
- `COMPLIANCE_MATRIX.md`: added R19 packaging/contract mapping

## Validation Targets

- `./prompt-dsl-system/tools/run.sh validate --repo-root .`
- `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
- `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`
