# R16 Performance Notes

## Smart Incremental Impact

- Expected improvement for repeated runs in short window:
  - avoid repeated filesystem scans when reuse gates pass
  - reduce `scan_time_s` in repeated discover/profile/diff/migrate invocations
- Reuse mode preserves new run identity (`new run_id`) while linking/copying prior artifacts.

## Guardrails

- Reuse is denied if prior run is stale, artifact-incomplete, or below cache-hit threshold.
- Strict default prevents reuse on fingerprint/VCS drift.
- Read-only snapshot-diff guard still runs in reuse mode.

## Observability

- Summary includes `smart_reused` and `reused_from`.
- `capabilities.json` embeds `smart` state and capability registry pointers.
