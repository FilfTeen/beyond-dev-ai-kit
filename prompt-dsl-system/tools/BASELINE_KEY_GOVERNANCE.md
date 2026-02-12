# Baseline Signing Key Governance

Scope: `prompt-dsl-system/tools/kit_integrity_manifest.json`, `prompt-dsl-system/tools/pipeline_trust_whitelist.json`.

## 1) Key model

- Signing mode:
  - `sha256` (default compatibility mode, no secret key required)
  - `hmac-sha256` (strict mode, requires signing key)
- Runtime key env:
  - default: `HONGZHI_BASELINE_SIGN_KEY`
  - optional override (wrapper strict flow): `HONGZHI_BASELINE_SIGN_KEY_ENV`
- Strict requirement switch:
  - `HONGZHI_BASELINE_REQUIRE_HMAC=1`

## 2) Rotation policy

- Rotation frequency:
  - production: at least every 90 days
  - pre-release/staging: at least every 30 days
- Rotation trigger:
  - suspected key leak
  - baseline tamper incident
  - personnel role change with signing access

## 3) Rotation procedure

1. Generate new key in secret manager (do not commit key value into repo).
2. Set CI/runtime env to new key.
3. Rebuild baseline files with new key:
   - `kit_integrity_guard.py build`
   - `pipeline_trust_guard.py build`
4. Verify with strict HMAC:
   - `--require-hmac true`
5. Prepare dual-approval evidence and merge.
6. Revoke old key in secret manager.

## 4) Incident handling

- On verification failure:
  - freeze promotion flow
  - restore trusted baseline from last known good commit
  - rotate signing key
  - rerun strict self-upgrade preflight and regression

## 5) Audit requirements

- Required artifacts per baseline-signing change:
  - `baseline_dual_approval.json` (approval evidence)
  - change ledger with reason + impact
  - rotation record: old key id -> new key id (IDs only, no raw key)
