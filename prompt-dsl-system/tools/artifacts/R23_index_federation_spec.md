# R23_index_federation_spec

## Name
Capability Index Federation (Round23)

## Purpose
Provide cross-repo, cross-run machine-queryable capability metadata in global state, while preserving governance and zero-write contracts.

## Files
- `<global_state_root>/federated_index.json`
- `<global_state_root>/federated_index.jsonl` (optional)
- `<global_state_root>/repos/<repo_fp>/index.json` (optional mirror)

All writes are atomic.

## Governance Rules
- Governance deny (`10/11/12`) is pre-dispatch hard block:
  - no writes to workspace/state/index/latest/run_meta/federated files.
- Federated scope gate (independent from command allow):
  - if token scope misses `federated_index`:
    - strict: `exit=24`, emit `HONGZHI_INDEX_BLOCK ...`, no federated write
    - non-strict: warn, emit `HONGZHI_INDEX_BLOCK ...`, no federated write

## Machine Lines
- Updated pointer:
  - `HONGZHI_INDEX <abs_path> package_version=... plugin_version=... contract_version=...`
- Block line:
  - `HONGZHI_INDEX_BLOCK code=24 reason=token_scope_missing command=... scope=federated_index token_scope=... ...`

## Federated Index Schema (high-level)
```json
{
  "version": "1.0.0",
  "updated_at": "2026-02-11T00:00:00Z",
  "repos": {
    "<repo_fp>": {
      "repo_fp": "<repo_fp>",
      "repo_root": "/abs/path",
      "last_seen_at": "...",
      "latest": {"run_id": "...", "timestamp": "...", "workspace": "...", "command": "discover"},
      "runs": [
        {
          "run_id": "...",
          "timestamp": "...",
          "command": "discover",
          "layout": "...",
          "metrics": {
            "module_candidates": 1,
            "endpoints_total": 6,
            "scan_time_s": 0.1,
            "ambiguity_ratio": 0.0,
            "confidence_tier": "high",
            "limits_hit": false,
            "hint_bundle_created": false,
            "hint_bundle_kind": "",
            "hint_bundle_expires_at": ""
          },
          "versions": {"package": "...", "plugin": "...", "contract": "..."},
          "governance": {"enabled": true, "token_used": false, "policy_hash": "..."}
        }
      ],
      "versions": {"package": "...", "plugin": "...", "contract": "..."},
      "governance": {"enabled": true, "token_used": false, "policy_hash": "..."},
      "layout": "...",
      "metrics": {}
    }
  }
}
```

## CLI
- `hongzhi-ai-kit index list --top-k 20`
- `hongzhi-ai-kit index query --keyword <kw> --endpoint <path> --top-k 10 [--strict] [--include-limits-hit]`
- `hongzhi-ai-kit index explain <repo_fp> <run_id>`

## Query Ranking
Rank order:
1. endpoint match
2. keyword match
3. recency
4. lower ambiguity_ratio
5. higher confidence tier

Strict query mode excludes `limits_hit=true` runs unless `--include-limits-hit` is provided.
