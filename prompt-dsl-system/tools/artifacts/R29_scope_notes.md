# R29 Scope Notes

## Behavior Summary
- Default behavior unchanged: company scope gate is disabled unless explicitly enabled.
- Additive machine signal:
  - all machine lines include `company_scope` for agent routing.
- Hard gate mode:
  - enable with `HONGZHI_REQUIRE_COMPANY_SCOPE=1`
  - mismatch returns exit `26` and `HONGZHI_GOV_BLOCK reason=company_scope_mismatch`

## Quick Commands
```bash
# default (gate off): should pass status with external scope marker
HONGZHI_PLUGIN_ENABLE=1 HONGZHI_COMPANY_SCOPE=external \
  hongzhi-ai-kit status --repo-root /path/to/repo

# gate on + mismatch: block with exit 26
HONGZHI_PLUGIN_ENABLE=1 HONGZHI_REQUIRE_COMPANY_SCOPE=1 HONGZHI_COMPANY_SCOPE=external \
  hongzhi-ai-kit discover --repo-root /path/to/repo

# gate on + match: allowed
HONGZHI_PLUGIN_ENABLE=1 HONGZHI_REQUIRE_COMPANY_SCOPE=1 HONGZHI_COMPANY_SCOPE=hongzhi-work-dev \
  hongzhi-ai-kit discover --repo-root /path/to/repo
```
