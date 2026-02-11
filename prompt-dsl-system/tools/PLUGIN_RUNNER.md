# PLUGIN_RUNNER.md — Hongzhi AI-Kit Plugin Runner

Version: 4.0.0 (R24 Hardening + Phase30)

## Install

```bash
cd /Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -e .
```

After install, both entry styles are available:

- `python3 -m hongzhi_ai_kit <subcommand> ...`
- `hongzhi-ai-kit <subcommand> ...`

Optional aliases (same behavior): `hzkit`, `hz`.

## Quick Start

```bash
# Governance status
hongzhi-ai-kit status --repo-root /path/to/project

# Discovery (governance checked)
export HONGZHI_PLUGIN_ENABLE=1
hongzhi-ai-kit discover --repo-root /path/to/project

# Discovery with smart incremental reuse
hongzhi-ai-kit discover \
  --repo-root /path/to/project \
  --smart --smart-max-age-seconds 600 --smart-min-cache-hit 0.90

# Discover with calibration thresholds
hongzhi-ai-kit discover \
  --repo-root /path/to/project \
  --min-confidence 0.60 \
  --ambiguity-threshold 0.80 \
  --emit-hints

# Hint loop: strict fails (21) -> apply hints rerun
hongzhi-ai-kit discover --repo-root /path/to/project --strict
# read HONGZHI_HINTS <abs_path> from stdout, then:
hongzhi-ai-kit discover \
  --repo-root /path/to/project \
  --apply-hints /abs/workspace/.../discover/hints.json \
  --hint-strategy aggressive \
  --strict

# Inline JSON hints (no file path required)
hongzhi-ai-kit discover \
  --repo-root /path/to/project \
  --apply-hints '{"kind":"profile_delta","repo_fingerprint":"<fp>","scope":["discover"],"delta":{"identity":{"keywords":["notice"]}}}' \
  --allow-cross-repo-hints

# Federated index list/query/explain
hongzhi-ai-kit index list --top-k 20
hongzhi-ai-kit index query --keyword notice --endpoint /notice --top-k 10
hongzhi-ai-kit index explain <repo_fp> <run_id>
```

## Governance & Security

The plugin enforces a strict governance model (enabled -> deny -> allow).

| Check | Behavior | Exit Code |
| --- | --- | --- |
| **Enabled** | Must be explicitly enabled via env or `policy.yaml` | **10** (Disabled) |
| **Deny List** | If `repo_root` matches `deny_roots` | **11** (Blocked) |
| **Allow List** | If `allow_roots` defined and `repo_root` NOT in it | **12** (Blocked) |
| **Policy Parse** | `policy.yaml` parse error (fail-closed) | **13** (Blocked) |
| **Permit Token** | `--permit-token <TOKEN>` bypasses allow/deny | **0** (Allowed) |

When blocked (10/11/12/13), the runner emits machine-readable stdout:

```text
HONGZHI_GOV_BLOCK code=<10|11|12|13> reason=<...> command=<...> package_version=<...> plugin_version=<...> contract_version=<...> detail=<json_quoted_string>
```

Hint bundle scope block line (strict mode can return exit `23`):

```text
HONGZHI_HINTS_BLOCK code=23 reason=token_scope_missing command=discover scope=<...> package_version=<...> plugin_version=<...> contract_version=<...> detail="..."
```

Federated index scope block line (strict mode can return exit `24`):

```text
HONGZHI_INDEX_BLOCK code=24 reason=token_scope_missing command=discover scope=federated_index token_scope=<...> package_version=<...> plugin_version=<...> contract_version=<...> detail="..."
```

### Permit Token v3 (TTL + Scope)

`--permit-token` supports plain string and JSON token formats.

- Plain token (backward compatible): `--permit-token "SKS-BYPASS"`
- JSON token:
  - `token`: required
  - `scope`: optional (`["status","discover"]` or `"discover,diff"`; default `"*"`)
    - when using federated index writes in command flow, include `federated_index` in scope
  - `expires_at`: optional ISO UTC timestamp
  - `issued_at` + `ttl_seconds`: optional TTL window

Example:

```bash
--permit-token '{"token":"T1","issued_at":"2026-02-11T00:00:00Z","ttl_seconds":600,"scope":["discover","status"]}'
```

If token expired or scope mismatches command, runner blocks with governance exit code (`12`).
If command is allowed but token scope misses `federated_index`:

- strict mode: exit `24` + `HONGZHI_INDEX_BLOCK ...`
- non-strict mode: warn + no federated index write

### Symlink / realpath hardening

- Allow/deny checks compare canonical real paths.
- Symlink-based path aliasing cannot bypass deny/allow policy checks.

Blocked runs must not write:

- `capabilities.json`
- `capabilities.jsonl`
- `capability_index.json`
- `latest.json`
- `run_meta.json`

Governance hard deny (`10/11/12/13`) must write nothing to:

- workspace artifacts (`capabilities.json`, `capabilities.jsonl`, hints)
- global state (`capability_index.json`, `latest.json`, `run_meta.json`, `federated_index.json`, `federated_index.jsonl`, repo mirrors)

For read-only subcommands (`status`, `index`), root resolution is zero-touch:

- no `.write_test` probing files
- no implicit directory creation in workspace/global-state roots

## Read-Only Contract

By default, the plugin never writes into target `repo_root`.

Enforcement:

1. snapshot before
2. snapshot after
3. any repo diff -> exit `3` (unless `--write-ok` explicitly set)

`--max-files` and `--max-seconds` only affect scan stage; read-only snapshot guard is always full-repo (non-truncated).

Output roots are additionally blocked from being placed under `repo_root`.

## Workspace vs Global State

- `workspace_root`: per-run artifacts and caches
- `global_state_root`: cross-run capability index and latest pointer

### Workspace root resolution

1. `~/Library/Caches/hongzhi-ai-kit/`
2. `~/.cache/hongzhi-ai-kit/`
3. `/tmp/hongzhi-ai-kit/`

### Global state root resolution

1. `~/Library/Application Support/hongzhi-ai-kit/`
2. `~/.hongzhi-ai-kit/`
3. `~/.cache/hongzhi-ai-kit/`
4. `/tmp/hongzhi-ai-kit/`

Overrides:

- `--workspace-root <path>`
- `--global-state-root <path>` (or env `HONGZHI_PLUGIN_GLOBAL_STATE_ROOT`)

## Smart Incremental

Supported commands: `discover`, `profile`, `diff`, `migrate`.

Parameters:

- `--smart`
- `--smart-max-age-seconds <N>` (default `600`)
- `--smart-min-cache-hit <ratio>` (default `0.90`)
- `--smart-max-fingerprint-drift <strict|warn>` (default `strict`)

`--smart` never bypasses governance and never bypasses read-only guard.

## Agent Contract

### v3 (kept for compatibility)

```text
hongzhi_ai_kit_summary version=3.0 command=discover fp=<...> run_id=<...> smart_reused=0 reused_from=- modules=1 endpoints=6 scan_time_s=0.12 governance=enabled
```

### v4 additions

1. stdout capability pointer line:

```text
HONGZHI_CAPS <abs_path_to_capabilities.json> path="<abs_path_to_capabilities.json>" package_version=<...> plugin_version=<...> contract_version=<...>
```

1.1 stdout hint bundle pointer line (when emitted):

```text
HONGZHI_HINTS <abs_path_to_discover/hints.json> path="<abs_path_to_discover/hints.json>" package_version=<...> plugin_version=<...> contract_version=<...>
```

2. status machine line:

```text
HONGZHI_STATUS package_version=<...> plugin_version=<...> contract_version=<...> enabled=<0|1> global_state_root="<abs_path>"
```

3. workspace append-only summary journal:

- `<workspace>/<fingerprint>/capabilities.jsonl`
- each line includes: `timestamp`, `command`, `repo_fp`, `run_id`, `exit_code`, `warnings_count`, `capabilities_path`

4. capability files on successful run:

- `<workspace>/<fingerprint>/<run_id>/capabilities.json`
- `<global_state_root>/capability_index.json`
- `<global_state_root>/<fingerprint>/latest.json`
- `<global_state_root>/<fingerprint>/runs/<run_id>/run_meta.json`
- `<global_state_root>/federated_index.json` (policy/scope gated)
- `<global_state_root>/federated_index.jsonl` (optional, policy-gated)
- `<global_state_root>/repos/<fingerprint>/index.json` (optional mirror, policy-gated)

`capabilities.json` includes version triple fields:

- `package_version`
- `plugin_version`
- `contract_version`

`version` key is retained for backward compatibility.

`capabilities.json` / `capabilities.jsonl` additionally expose machine fields for agent planning:

- `layout`
- `module_candidates`
- `ambiguity_ratio`
- `limits_hit`
- `limits` (`max_files`, `max_seconds`, reason fields)
- `scan_stats` (`files_scanned`, cache counters, cache hit rate)
- `scan_io_stats` (`layout_adapter_runs`, `java_files_scanned`, `templates_scanned`, `snapshot_files_count`, cache counters)
- `layout_details` (`adapter_used`, roots detection details, fallback reason)
- `hints` (`emitted`, `applied`, `bundle_path`, `source_path`, `strategy`, `hint_effective`, `confidence_delta`)
- `calibration`:
  - `needs_human_hint`
  - `confidence`
  - `confidence_tier`
  - `reasons[]` (enum style)
  - `suggested_hints_path` / `report_path`

`hongzhi_ai_kit_summary` includes:

- `needs_human_hint`
- `confidence_tier`
- `ambiguity_ratio`
- `exit_hint`
- `limits_hit` and `limits_reason`
- `reuse_validated`
- `hint_applied` and `hint_bundle`
- `hint_effective` and `confidence_delta`

### Federated Index (R23)

Global state federated files:

- `federated_index.json` (atomic write)
- `federated_index.jsonl` (optional append log, atomic update)
- `repos/<fp>/index.json` (optional repo mirror)

`federated_index.json` stores per-repo entries with:

- `repo_fp`
- `last_seen_at`
- `latest` pointer
- bounded `runs[]`
- `versions` (`package`, `plugin`, `contract`)
- `governance` (`enabled`, `token_used`, `policy_hash`)
- run `layout` + `metrics` (including hint bundle flags / limits / confidence)

Machine-readable pointer when updated:

```text
HONGZHI_INDEX <abs_path_to_federated_index.json> path="<abs_path_to_federated_index.json>" package_version=<...> plugin_version=<...> contract_version=<...>
```

Policy schema extension:

```yaml
plugin:
  enabled: true
  federated_index:
    enabled: true           # default: inherit plugin.enabled
    write_jsonl: true       # optional
    write_repo_mirror: true # optional
```

## Calibration Layer (R20)

Discover now emits workspace-only calibration artifacts:

- `<workspace>/<fp>/<run_id>/calibration/calibration_report.json`
- `<workspace>/<fp>/<run_id>/calibration/calibration_report.md`
- `<workspace>/<fp>/<run_id>/calibration/hints_suggested.yaml` (default enabled; can disable via `--no-emit-hints`)

New discover flags:

- `--min-confidence <float>` (default `0.60`)
- `--ambiguity-threshold <float>` (default `0.80`)
- `--emit-hints` / `--no-emit-hints`
- `--apply-hints <path>` (json/yaml hint bundle from workspace)
- `--apply-hints <path-or-inline-json>` (supports path or inline JSON string)
- `--hint-strategy conservative|aggressive` (default `conservative`)
- `--allow-cross-repo-hints` (bypass repo_fingerprint match on apply)
- `--hint-bundle-ttl-seconds <N>` (default `1800`)

Strict behavior:

- if calibration yields `needs_human_hint=true` and `--strict` is set, discover exits `21`.
- `HONGZHI_CAPS` is still emitted (workspace-only artifacts remain available for agent/human follow-up).

Backfill flow:

1. Read `calibration/hints_suggested.yaml`.
2. Copy minimal values into declared profile identity hints (`backend_package_hint`, `web_path_hint`, `keywords`).
3. Re-run `discover` with optional `--keywords` to reduce ambiguity.

## Hint Loop + Layout Adapters (R21)

- Strict discover with `needs_human_hint=1` emits:
  - `HONGZHI_HINTS <abs_path>`
  - workspace hint bundle: `<workspace>/<fp>/<run_id>/discover/hints.json`
  - summary fields: `hint_bundle=...` and `hint_applied=0`
- Rerun with `--apply-hints` will bias module ranking and root inference without writing target repo.
- Layout adapters v1 extends root detection for:
  - Maven multi-module (`<root>/<module>/src/main/java`)
  - Non-standard Java roots (`java/`, `app/src/main/java`, `backend/src/main/java`)
- Capabilities expose adapter evidence via `layout` + `layout_details`.

## Hint Assetization (R22)

- Discover hint loop now emits a typed bundle with `kind=profile_delta`.
- Bundle verification on apply:
  - expiry check (`expires_at` / `ttl_seconds`)
  - `repo_fingerprint` check (unless `--allow-cross-repo-hints`)
  - scope check (`scope` includes `discover` or `*`)
- Capabilities include additive `hint_bundle` contract:
  - `kind`, `path`, `verified`, `expired`, `ttl_seconds`, `created_at`, `expires_at`
- Summary line additive fields:
  - `hint_bundle_kind`, `hint_verified`, `hint_expired`

### Capability Index v1 (global state)

`capability_index.json` project entry includes:

- `repo_fingerprint`
- `created_at`
- `latest`
- `runs[]`
- `versions` (`package`, `plugin`, `contract`)
- `governance` (`enabled`, `token_used`, `policy_hash`)

## Exit Codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | General error |
| 2 | Strict mode violation |
| 3 | Read-only contract violation |
| 20 | Limits hit in strict mode |
| 21 | Strict calibration gate hit (`needs_human_hint=true`) |
| 22 | Strict hint verification failure (e.g., expired/invalid apply-hints bundle) |
| 23 | Strict hint-bundle emission blocked by token scope (missing `hint_bundle`) |
| 24 | Strict federated-index write blocked by token scope (missing `federated_index`) |
| 10 | Plugin disabled |
| 11 | Repo denied by policy |
| 12 | Repo not in allow list |

## Cleanup

```bash
hongzhi-ai-kit clean
hongzhi-ai-kit clean --older-than 3
```
