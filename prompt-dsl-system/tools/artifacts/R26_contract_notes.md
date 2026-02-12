# R26 Contract Notes

## Additive Machine-Line Contract
R26 extends pointer lines with additive `json='...'` payloads:
- `HONGZHI_CAPS ... json='...'
- `HONGZHI_INDEX ... json='...'
- `HONGZHI_HINTS ... json='...'

Payload keys (minimum):
- `path`
- `command`
- `versions {package, plugin, contract}`
- `repo_fingerprint`
- `run_id`

Legacy fields remain unchanged:
- leading prefix token
- second-token path fallback
- `path="..."`
- version triplet fields

## Summary Additions
`hongzhi_ai_kit_summary` now includes additive:
- `mismatch_reason`
- `mismatch_detail`

## mismatch_reason enum
- `schema_version_mismatch`
- `fingerprint_mismatch`
- `producer_version_mismatch`
- `cache_corrupt`
- `unknown`

## Compatibility Safety Switch
To temporarily suppress `json='...'` while keeping legacy machine fields:
- `export HONGZHI_MACHINE_JSON_ENABLE=0`
