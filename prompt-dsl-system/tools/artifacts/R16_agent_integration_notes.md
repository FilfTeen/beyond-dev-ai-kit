# R16 Agent Integration Notes

## Read Order for Agent

1. Parse stdout summary line:
   - `hongzhi_ai_kit_summary ...`
2. Read run-local capability output:
   - `<workspace>/capabilities.json`
3. Read global index for cross-run memory:
   - `<global_state_root>/capability_index.json`
4. Resolve latest pointer for project fingerprint:
   - `<global_state_root>/<fp>/latest.json`
5. Optional audit metadata:
   - `<global_state_root>/<fp>/runs/<run_id>/run_meta.json`

## Practical Contract Fields

- `capabilities.json.smart.reused`
- `capabilities.json.smart.reused_from_run_id`
- `capabilities.json.capability_registry.index_path`
- `capabilities.json.capability_registry.latest_path`
- `capabilities.json.capability_registry.run_meta_path`

## Safety Notes

- If command exits with governance block (10/11/12), agent must treat capability state as unchanged.
- Global state files are outside business repo and are not project contamination.
