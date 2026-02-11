# A2_R24_change_ledger

## Changed Files
- `prompt-dsl-system/tools/hongzhi_plugin.py`
- `prompt-dsl-system/tools/hongzhi_ai_kit/paths.py`
- `prompt-dsl-system/tools/hongzhi_ai_kit/capability_store.py`
- `prompt-dsl-system/tools/hongzhi_ai_kit/federated_store.py`
- `prompt-dsl-system/tools/structure_discover.py`
- `prompt-dsl-system/tools/golden_path_regression.sh`
- `prompt-dsl-system/tools/_tmp_structure_cases/case8_composed_annotation/src/main/java/com/example/composed/annotation/ComposedList.java`
- `prompt-dsl-system/tools/_tmp_structure_cases/case8_composed_annotation/src/main/java/com/example/composed/controller/ComposedController.java`
- `prompt-dsl-system/tools/_tmp_structure_cases/case8_composed_annotation/src/main/java/com/example/composed/service/ComposedService.java`
- `prompt-dsl-system/tools/_tmp_structure_cases/case8_composed_annotation/src/main/resources/templates/composed/index.html`
- `prompt-dsl-system/tools/PLUGIN_RUNNER.md`
- `prompt-dsl-system/00_conventions/FACT_BASELINE.md`
- `prompt-dsl-system/00_conventions/COMPLIANCE_MATRIX.md`

## Key Deltas
- Added policy parse fail-closed gate with exit code `13`.
- Added read-only path resolver mode and wired status/index to zero-touch behavior.
- Enforced full snapshot read-only guard independent of scan limits.
- Added parse-safe machine path field (`path=`) while preserving legacy token order.
- Hardened JSON/JSONL concurrent write behavior.
- Added discover I/O telemetry (`scan_io_stats`) and hints effectiveness telemetry.
- Extended endpoint extraction for composed/symbolic mappings.
- Added Phase30 regression suite (8 checks), all pass.

## Validation Evidence
- `./prompt-dsl-system/tools/run.sh validate --repo-root .` => Errors=0, Warnings=0
- `HONGZHI_VALIDATE_STRICT=1 ./prompt-dsl-system/tools/run.sh validate --repo-root .` => Errors=0, Warnings=0
- `bash prompt-dsl-system/tools/golden_path_regression.sh --repo-root .` => 86/86 PASS
