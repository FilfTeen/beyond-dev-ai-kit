# PLUGIN_RUNNER.md — Hongzhi AI-Kit Plugin Runner

Version: 3.0.0 (R16 Agent-Native Capability Layer)

## Quick Start (macOS)

```bash
# Installable package usage
export PYTHONPATH=$PYTHONPATH:/path/to/prompt-dsl-system/tools
python3 -m hongzhi_ai_kit status

# Discovery (governance checked)
export HONGZHI_PLUGIN_ENABLE=1
python3 -m hongzhi_ai_kit discover --repo-root /path/to/project

# Discovery with smart incremental reuse
python3 -m hongzhi_ai_kit discover \
  --repo-root /path/to/project \
  --smart --smart-max-age-seconds 600 --smart-min-cache-hit 0.90

# Direct script usage (legacy)
python3 tools/hongzhi_plugin.py discover --repo-root /path/to/project
```

## Governance & Security

The plugin enforces a strict governance model (enabled -> deny -> allow).

| Check | Behavior | Exit Code |
| --- | --- | --- |
| **Enabled** | Must be explicitly enabled via env or `policy.yaml` | **10** (Disabled) |
| **Deny List** | If `repo_root` matches `deny_roots` | **11** (Blocked) |
| **Allow List** | If `allow_roots` defined and `repo_root` NOT in it | **12** (Blocked) |
| **Permit Token** | `--permit-token <TOKEN>` bypasses checks | **0** (Allowed) |

Critical rule (R16): if governance denies execution (10/11/12), plugin must not write global capability state (`capability_index.json`, `latest.json`, `run_meta.json`).

### Status Command

Use `status` to check governance state and capability registry locations without running a scan:

```bash
python3 -m hongzhi_ai_kit status --repo-root /path/to/check
```

## Read-Only Contract

By default, the plugin **never writes** into the target project repo.
Enforcement is via **snapshot-diff guard**:

1. Before running, takes a lightweight snapshot of `repo_root` (relpath, size, mtime_ns)
2. After completion, takes a second snapshot
3. If any file was created/deleted/modified -> **exit code 3**

Override with `--write-ok` if intentional writes are needed.

## Workspace vs Global State

Two distinct roots are used:

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

Optional overrides:

- `--workspace-root <path>`
- `--global-state-root <path>` (or env `HONGZHI_PLUGIN_GLOBAL_STATE_ROOT`)

## Smart Incremental (`--smart`)

Supported commands: `discover`, `profile`, `diff`, `migrate`.

Parameters:

- `--smart`
- `--smart-max-age-seconds <N>` (default `600`)
- `--smart-min-cache-hit <ratio>` (default `0.90`)
- `--smart-max-fingerprint-drift <strict|warn>` (default `strict`)

Reuse requires all mandatory conditions:

1. Capability index contains prior success for the project
2. Age within `smart-max-age-seconds`
3. Fingerprint/VCS policy satisfied
4. Prior workspace and expected artifacts exist
5. Cached hit rate is known and above threshold (or non-strict warning path)

`--smart` never bypasses governance and never bypasses read-only guard.

## Agent-Detectable Contract v3

Each successful run writes:

1. `<workspace>/capabilities.json`
2. `<global_state_root>/capability_index.json`
3. `<global_state_root>/<fingerprint>/latest.json`
4. `<global_state_root>/<fingerprint>/runs/<run_id>/run_meta.json`

### Single-line stdout summary

```text
hongzhi_ai_kit_summary version=3.0 command=discover fp=<...> run_id=<...> smart_reused=0 reused_from=- modules=1 endpoints=6 scan_time_s=0.12 governance=enabled
```

### capabilities.json v3 additions

- `smart: { enabled, reused, reused_from_run_id }`
- `capability_registry: { global_state_root, index_path, latest_path, run_meta_path, updated }`

## Exit Codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | General error |
| 2 | Strict mode violation (ambiguity) |
| 3 | Read-only contract violation |
| 10 | Plugin disabled (governance) |
| 11 | Repo denied by policy |
| 12 | Repo not allowed by policy |

## Cleanup

```bash
# Remove runs older than 7 days (default)
python3 -m hongzhi_ai_kit clean

# Remove runs older than N days
python3 -m hongzhi_ai_kit clean --older-than 3
```
