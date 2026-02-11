# A2_verification_checklist

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b

## Structural Verification
- [ ] Tables created: PUBLIC_NOTICE, PUBLIC_NOTICE_SCOPE, PUBLIC_NOTICE_COVER, PUBLIC_NOTICE_EXTERNAL_SOURCE, PUBLIC_NOTICE_READ
- [ ] Primary keys and unique constraints exist as defined
- [ ] Indexes from 06_create_index.sql exist

## Data/Config Verification
- [ ] `SYS_MENU_INFO` rows for 30837/30838 inserted as expected
- [ ] `SYS_ROLE_MENU` mappings inserted without duplication errors
- [ ] No unauthorized object outside module scope changed

## Acceptance Mapping
- [ ] A1 portability audit reviewed
- [ ] A2 converted SQL executable in DM8 dry run
- [ ] A3 performance/index risks accepted or mitigated
- [ ] Runbook and rollback plan approved
