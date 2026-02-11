# A1 Impact Tree

## Goal

Round17 plugin-level hardening for `hongzhi_ai_kit`: installable, governed, read-only by default, machine-readable outputs.

## Change Tree

- Packaging layer
  - `pyproject.toml` (editable install + console scripts)
  - `setup.py` (legacy pip editable compatibility)
  - `hongzhi_ai_kit/cli.py` import chain fallback
- Runtime contract layer
  - `hongzhi_plugin.py` adds:
    - `HONGZHI_CAPS <abs_path>` stdout line
    - `capabilities.jsonl` append-only journal
    - `HONGZHI_GOV_BLOCK ...` machine-readable governance block line
  - keep v3 summary line for backward compatibility
- Governance/read-only layer
  - reject runs (10/11/12) keep zero artifact writes
  - output roots blocked from being under target repo
- Integration layer
  - new governance skill: plugin runner orchestration
  - new discover pipeline for status->discover->capabilities read flow
- Validation layer
  - regression Phase23 adds packaging/module/console/contract checks
  - uninstalled install-hint check added

## Risk Focus

- Version drift between package metadata and runtime version
- False-positive green when module import depends on ambient `PYTHONPATH`
- Accidental writes under governance-blocked runs
