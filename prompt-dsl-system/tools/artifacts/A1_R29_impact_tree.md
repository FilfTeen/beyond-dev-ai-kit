# A1_R29 Impact Tree

## Scope
Round29 (minimal intrusion) targets:
1. Company scope signal in machine-readable outputs.
2. Optional company-scope hard gate (default off).
3. Governance skill lifecycle convergence to deployed.
4. Regression hard gate expansion with Phase35.

## Change Nodes
- Runtime contract node:
  - `hongzhi_plugin.py` machine lines + summary + capabilities/jsonl include `company_scope`.
- Governance gate node:
  - Optional scope check (`HONGZHI_REQUIRE_COMPANY_SCOPE=1`) with `exit=26` on mismatch.
- Registry lifecycle node:
  - `skills.json` governance plugin skills moved to `deployed`.
- Regression node:
  - `golden_path_regression.sh` Phase35 (6 checks).
- Contract schema node:
  - `contract_schema_v1.json` adds `company_scope` requirements and `exit 26` mapping.

## Risk Surface
- Compatibility risk: low (additive-only fields, default gate disabled).
- Governance risk: low (mismatch path explicitly zero-write, covered by Phase35).
- Parsing risk: low (existing keys unchanged; new field additive).

## Guardrails
- Existing Phase1~34 preserved.
- New Phase35 verifies:
  - lifecycle convergence,
  - machine output presence,
  - default-off behavior,
  - mismatch hard block + zero-write,
  - required-match allow path.
