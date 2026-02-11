# PLUGIN_RUNNER.md — Hongzhi AI-Kit Plugin Runner

Version: 4.0.0 (R20 Calibration Layer + Needs-Human-Hint Gate)

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
```

## Governance & Security

The plugin enforces a strict governance model (enabled -> deny -> allow).

| Check | Behavior | Exit Code |
| --- | --- | --- |
| **Enabled** | Must be explicitly enabled via env or `policy.yaml` | **10** (Disabled) |
| **Deny List** | If `repo_root` matches `deny_roots` | **11** (Blocked) |
| **Allow List** | If `allow_roots` defined and `repo_root` NOT in it | **12** (Blocked) |
| **Permit Token** | `--permit-token <TOKEN>` bypasses allow/deny | **0** (Allowed) |

When blocked (10/11/12), the runner emits machine-readable stdout:

```text
HONGZHI_GOV_BLOCK code=<10|11|12> reason=<...> command=<...> package_version=<...> plugin_version=<...> contract_version=<...> detail="..."
```

### Permit Token v3 (TTL + Scope)

`--permit-token` supports plain string and JSON token formats.

- Plain token (backward compatible): `--permit-token "SKS-BYPASS"`
- JSON token:
  - `token`: required
  - `scope`: optional (`["status","discover"]` or `"discover,diff"`; default `"*"`)
  - `expires_at`: optional ISO UTC timestamp
  - `issued_at` + `ttl_seconds`: optional TTL window

Example:

```bash
--permit-token '{"token":"T1","issued_at":"2026-02-11T00:00:00Z","ttl_seconds":600,"scope":["discover","status"]}'
```

If token expired or scope mismatches command, runner blocks with governance exit code (`12`).

### Symlink / realpath hardening

- Allow/deny checks compare canonical real paths.
- Symlink-based path aliasing cannot bypass deny/allow policy checks.

Blocked runs must not write:

- `capabilities.json`
- `capabilities.jsonl`
- `capability_index.json`
- `latest.json`
- `run_meta.json`

## Read-Only Contract

By default, the plugin never writes into target `repo_root`.

Enforcement:

1. snapshot before
2. snapshot after
3. any repo diff -> exit `3` (unless `--write-ok` explicitly set)

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
HONGZHI_CAPS <abs_path_to_capabilities.json> package_version=<...> plugin_version=<...> contract_version=<...>
```

2. status machine line:

```text
HONGZHI_STATUS package_version=<...> plugin_version=<...> contract_version=<...> enabled=<0|1>
```

3. workspace append-only summary journal:

- `<workspace>/<fingerprint>/capabilities.jsonl`
- each line includes: `timestamp`, `command`, `repo_fp`, `run_id`, `exit_code`, `warnings_count`, `capabilities_path`

4. capability files on successful run:

- `<workspace>/<fingerprint>/<run_id>/capabilities.json`
- `<global_state_root>/capability_index.json`
- `<global_state_root>/<fingerprint>/latest.json`
- `<global_state_root>/<fingerprint>/runs/<run_id>/run_meta.json`

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

## Calibration Layer (R20)

Discover now emits workspace-only calibration artifacts:

- `<workspace>/<fp>/<run_id>/calibration/calibration_report.json`
- `<workspace>/<fp>/<run_id>/calibration/calibration_report.md`
- `<workspace>/<fp>/<run_id>/calibration/hints_suggested.yaml` (default enabled; can disable via `--no-emit-hints`)

New discover flags:

- `--min-confidence <float>` (default `0.60`)
- `--ambiguity-threshold <float>` (default `0.80`)
- `--emit-hints` / `--no-emit-hints`

Strict behavior:

- if calibration yields `needs_human_hint=true` and `--strict` is set, discover exits `21`.
- `HONGZHI_CAPS` is still emitted (workspace-only artifacts remain available for agent/human follow-up).

Backfill flow:

1. Read `calibration/hints_suggested.yaml`.
2. Copy minimal values into declared profile identity hints (`backend_package_hint`, `web_path_hint`, `keywords`).
3. Re-run `discover` with optional `--keywords` to reduce ambiguity.

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
| 10 | Plugin disabled |
| 11 | Repo denied by policy |
| 12 | Repo not in allow list |

## Cleanup

```bash
hongzhi-ai-kit clean
hongzhi-ai-kit clean --older-than 3
```
