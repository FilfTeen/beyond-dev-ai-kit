# A3_R24_rollback_plan

## Rollback Trigger
- Any regression in governance zero-write, read-only guard, machine-line parsing, or concurrency stability.

## Rollback Steps
1. Revert Round24 code paths:
- `prompt-dsl-system/tools/hongzhi_plugin.py`
- `prompt-dsl-system/tools/hongzhi_ai_kit/paths.py`
- `prompt-dsl-system/tools/hongzhi_ai_kit/capability_store.py`
- `prompt-dsl-system/tools/hongzhi_ai_kit/federated_store.py`
- `prompt-dsl-system/tools/structure_discover.py`

2. Revert regression additions:
- Remove Phase30 block from `prompt-dsl-system/tools/golden_path_regression.sh`.
- Remove helper functions introduced for machine-path parsing/snapshots if only used by Phase30.

3. Revert fixtures:
- Remove `prompt-dsl-system/tools/_tmp_structure_cases/case8_composed_annotation/`.

4. Revert docs/baselines:
- `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
- `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
- `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`

5. Re-run gates after rollback:
- `./prompt-dsl-system/tools/run.sh validate --repo-root .`
- `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .`
- `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .`

## Risk Notes
- Rolling back atomic write hardening may reintroduce concurrent write races.
- Rolling back full snapshot guard may reintroduce `--max-files` blind spot for read-only violations.
