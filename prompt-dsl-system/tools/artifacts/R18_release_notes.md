# R18_release_notes

## Highlights
- Version triplet contract is now explicit and machine-readable across plugin outputs:
  - `package_version`
  - `plugin_version`
  - `contract_version`
- Added machine status line:
  - `HONGZHI_STATUS package_version=... plugin_version=... contract_version=... enabled=...`
- Extended machine capability pointer line:
  - `HONGZHI_CAPS <abs_path> package_version=... plugin_version=... contract_version=...`
- Extended governance block line while preserving exit code semantics:
  - `HONGZHI_GOV_BLOCK code=... ... package_version=... plugin_version=... contract_version=...`
- `capabilities.json` and `capabilities.jsonl` now persist version triplet metadata.

## Build / Install

### Editable install
```bash
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -e .
```

### Build artifacts
```bash
python3 -m pip install --upgrade build
python3 -m build
```

### Wheel smoke (fresh venv)
```bash
python3 -m venv /tmp/hz_build_venv
source /tmp/hz_build_venv/bin/activate
python3 -m pip install dist/*.whl
hongzhi-ai-kit --help
python3 -m hongzhi_ai_kit --help
```

## Governance / Exit Codes
- `3`: read-only contract violation (repo mutated)
- `10`: plugin disabled
- `11`: denylist blocked
- `12`: allowlist mismatch blocked

## Regression Gate
- Golden regression now includes Phase24 (+5 checks).
- Current total: **47 checks**, all PASS.
