# PLUGIN_RUNNER.md — Hongzhi AI-Kit Plugin Runner

Version: 1.1.0 (R29 Company Scope Gate + Phase35)

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

# Control additive machine-line json field (default on)
hongzhi-ai-kit status --repo-root /path/to/project --machine-json 1
# env override has higher priority
HONGZHI_MACHINE_JSON_ENABLE=0 hongzhi-ai-kit status --repo-root /path/to/project --machine-json 1

# Company scope marker (additive machine field, default: hongzhi-work-dev)
hongzhi-ai-kit status --repo-root /path/to/project --company-scope hongzhi-work-dev
# Optional hard gate (default off): mismatch -> exit 26
HONGZHI_REQUIRE_COMPANY_SCOPE=1 HONGZHI_COMPANY_SCOPE=hongzhi-work-dev \
  hongzhi-ai-kit discover --repo-root /path/to/project

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

# Build unified scan graph (workspace-only)
hongzhi-ai-kit scan-graph --repo-root /path/to/project

# Reuse discover scan_graph in profile/diff
hongzhi-ai-kit profile --repo-root /path/to/project --module-key notice --scan-graph /abs/ws/.../discover/scan_graph.json
hongzhi-ai-kit diff --old-project-root /path/old --new-project-root /path/new --module-key notice \
  --old-scan-graph /abs/ws/old_scan_graph.json --new-scan-graph /abs/ws/new_scan_graph.json
```

## Governance & Security

The plugin enforces a strict governance model (enabled -> deny -> allow).

| Check | Behavior | Exit Code |
| --- | --- | --- |
| **Enabled** | Must be explicitly enabled via env or `policy.yaml` | **10** (Disabled) |
| **Deny List** | If `repo_root` matches `deny_roots` | **11** (Blocked) |
| **Allow List** | If `allow_roots` defined and `repo_root` NOT in it | **12** (Blocked) |
| **Policy Parse** | `policy.yaml` parse error (fail-closed) | **13** (Blocked) |
| **Company Scope** | Optional required scope mismatch (`HONGZHI_REQUIRE_COMPANY_SCOPE=1`) | **26** (Blocked) |
| **Permit Token** | `--permit-token <TOKEN>` bypasses allow/deny | **0** (Allowed) |
| **Scan Graph Mismatch** | strict spot-check detects scan_graph mismatch | **25** |

When blocked (10/11/12/13/26), the runner emits machine-readable stdout:

```text
HONGZHI_GOV_BLOCK code=<10|11|12|13|26> reason=<...> command=<...> company_scope="<...>" package_version=<...> plugin_version=<...> contract_version=<...> detail=<json_quoted_string>
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
HONGZHI_CAPS <abs_path_to_capabilities.json> path="<abs_path_to_capabilities.json>" json='{"path":"...","command":"discover","versions":{"package":"...","plugin":"...","contract":"..."},"repo_fingerprint":"...","run_id":"..."}' mismatch_reason=<...> mismatch_detail="<...>" package_version=<...> plugin_version=<...> contract_version=<...>
```

1.1 stdout hint bundle pointer line (when emitted):

```text
HONGZHI_HINTS <abs_path_to_discover/hints.json> path="<abs_path_to_discover/hints.json>" json='{"path":"...","command":"discover","versions":{"package":"...","plugin":"...","contract":"..."},"repo_fingerprint":"...","run_id":"..."}' package_version=<...> plugin_version=<...> contract_version=<...>
```

`json='...'` is additive and enabled by default.  
Temporary fallback switch: set `HONGZHI_MACHINE_JSON_ENABLE=0` to suppress `json=` field without changing legacy parsers.
CLI toggle is also available: `--machine-json 0|1` (env override wins if both are set).

### Contract schema + validator (zero deps)

- Contract schema file:
  - `prompt-dsl-system/tools/contract_schema_v1.json`
- Validator script:
  - `prompt-dsl-system/tools/contract_validator.py`

Examples:

```bash
# Validate machine-lines from discover stdout
HONGZHI_PLUGIN_ENABLE=1 hongzhi-ai-kit discover --repo-root /path/to/project --machine-json 1 \
  | python3 prompt-dsl-system/tools/contract_validator.py --stdin

# Validate machine-lines from an existing log file
python3 prompt-dsl-system/tools/contract_validator.py \
  --schema prompt-dsl-system/tools/contract_schema_v1.json \
  --file /tmp/hz_discover_stdout.log
```

Validator output contract:

- success: `CONTRACT_OK=1 ...` and exit `0`
- failure: `CONTRACT_OK=0 CONTRACT_ERR=<code> CONTRACT_MSG=\"...\"` and exit `2`

1. status machine line:

```text
HONGZHI_STATUS package_version=<...> plugin_version=<...> contract_version=<...> enabled=<0|1> global_state_root="<abs_path>"
HONGZHI_STATUS ... company_scope="<hongzhi-work-dev>" company_scope_required=<0|1> ...
```

1. workspace append-only summary journal:

- `<workspace>/<fingerprint>/capabilities.jsonl`
- each line includes: `timestamp`, `command`, `repo_fp`, `run_id`, `exit_code`, `warnings_count`, `capabilities_path`

1. capability files on successful run:

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
- `scan_graph` (`used`, `cache_key`, `cache_hit_rate`, `java_files_indexed`, `bytes_read`, `io_stats`)
- `scan_graph.schema_version`, `scan_graph.producer_versions`, `scan_graph.graph_fingerprint`
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
- `mismatch_reason` and `mismatch_detail`
- `scan_graph_used`, `scan_cache_hit_rate`, `java_files_indexed`, `bytes_read`

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
HONGZHI_INDEX <abs_path_to_federated_index.json> path="<abs_path_to_federated_index.json>" json='{"path":"...","command":"discover","versions":{"package":"...","plugin":"...","contract":"..."},"repo_fingerprint":"...","run_id":"..."}' mismatch_reason=<...> mismatch_detail="<...>" package_version=<...> plugin_version=<...> contract_version=<...>
```

Block/status lines also expose additive `json='...'` with the same encoding function:

- `HONGZHI_STATUS`
- `HONGZHI_GOV_BLOCK`
- `HONGZHI_INDEX_BLOCK`
- `HONGZHI_HINTS_BLOCK`

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

## Unified Scan Graph v1.1 (R26 additive)

- `scan_graph.json` now includes additive metadata:
  - `schema_version`
  - `producer_versions` (`package_version`, `plugin_version`, `contract_version`)
  - `graph_fingerprint` (stable fingerprint on roots + file index meta)
- Strict mismatch (`exit=25`) now emits explainable fields:
  - summary: `mismatch_reason`, `mismatch_detail`
  - summary and pointers add `mismatch_suggestion`
  - `HONGZHI_CAPS` / `HONGZHI_INDEX`: additive `mismatch_reason`, `mismatch_detail`, `mismatch_suggestion`

`mismatch_reason` enum:

- `schema_version_mismatch`
- `producer_version_mismatch`
- `fingerprint_mismatch`
- `corrupted_cache`
- `unknown`
- `profile` / `diff` default to reusing latest discover scan graph when available; hot reuse reports command-local no-rescan counters (`java_files_indexed=0`, `bytes_read=0`) while preserving source index stats in additive fields.

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
| 25 | Strict scan-graph mismatch gate (schema/fingerprint/version/consistency mismatch) |
| 26 | Company scope mismatch (only when company-scope hard gate is enabled) |
| 13 | Policy parse error (fail-closed) |
| 10 | Plugin disabled |
| 11 | Repo denied by policy |
| 12 | Repo not in allow list |

## Cleanup

```bash
hongzhi-ai-kit clean
hongzhi-ai-kit clean --older-than 3
```
