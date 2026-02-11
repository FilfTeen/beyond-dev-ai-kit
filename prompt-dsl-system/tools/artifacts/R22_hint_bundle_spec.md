# R22_hint_bundle_spec

## Name
`profile_delta` hint bundle (Round22)

## Purpose
A machine-readable workspace artifact used by discover Hint Loop to carry minimal reusable correction hints without touching target repo files.

## File Location
- emitted under workspace run directory:
  - `<workspace>/<fp>/<run_id>/discover/hints.json`

## Top-level Schema (JSON)
```json
{
  "version": "1.0.0",
  "kind": "profile_delta",
  "created_at": "2026-02-11T00:00:00Z",
  "expires_at": "2026-02-11T00:30:00Z",
  "ttl_seconds": 1800,
  "repo_fingerprint": "<fp>",
  "scope": ["discover", "hint_bundle"],
  "source": {
    "run_id": "<run_id>",
    "command": "discover",
    "needs_human_hint": true,
    "confidence": 0.41,
    "confidence_tier": "low",
    "reasons": ["..."]
  },
  "delta": {
    "identity": {
      "backend_package_hint": "com.example.notice",
      "web_path_hint": "backstage/notice",
      "keywords": ["notice"]
    },
    "roots": {
      "backend_java": ["src/main/java/com/example/notice"],
      "web_template": ["src/main/resources/templates/backstage/notice"]
    },
    "layout": {
      "layout": "multi-module-maven",
      "adapter_used": "layout_adapters_v1"
    }
  },
  "rerun": {
    "hint_strategy_default": "conservative",
    "command_template": "hongzhi-ai-kit discover --repo-root <repo_root> --apply-hints <abs_path>"
  }
}
```

## Apply Verification Rules
When `--apply-hints` is used:
1. Accept input as file path or inline JSON string.
2. Verify kind is `profile_delta`.
3. Verify expiry (`expires_at` or `created_at + ttl_seconds`).
4. Verify `repo_fingerprint` unless `--allow-cross-repo-hints` is set.
5. Verify scope includes current command (`discover`) or `*`.

## Strict Exit Semantics
- `21`: discover calibration needs human hint.
- `22`: apply-hints verify failure (e.g., expired bundle).
- `23`: hint bundle emission blocked by token scope (`hint_bundle` missing).

## Machine Lines
- bundle pointer:
  - `HONGZHI_HINTS <abs_path> ...`
- bundle block:
  - `HONGZHI_HINTS_BLOCK code=23 reason=token_scope_missing ...`

## Capability Contract Additions
- `capabilities.json` and `capabilities.jsonl` include:
  - `hint_bundle {kind,path,verified,expired,ttl_seconds,created_at,expires_at}`
- summary line includes:
  - `hint_bundle_kind`, `hint_verified`, `hint_expired`
