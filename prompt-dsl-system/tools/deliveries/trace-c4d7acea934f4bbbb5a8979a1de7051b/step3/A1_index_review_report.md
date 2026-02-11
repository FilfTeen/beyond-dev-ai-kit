# A1_index_review_report

- context_id: ctx-3a70562661bc
- trace_id: trace-c4d7acea934f4bbbb5a8979a1de7051b
- input_artifact_refs: ["A2"]

## Index Inventory
- IDX_PN_STATUS ON PUBLIC_NOTICE (STATUS)
- IDX_PN_PUBLISH_TIME ON PUBLIC_NOTICE (PUBLISH_TIME)
- IDX_PN_AUDIT_ORG ON PUBLIC_NOTICE (AUDIT_ORG_ID)
- IDX_PN_PUBLISHER_ORG ON PUBLIC_NOTICE (PUBLISHER_ORG_ID)
- IDX_PN_COMMUNITY ON PUBLIC_NOTICE (COMMUNITY_ID)
- IDX_PN_STREET ON PUBLIC_NOTICE (STREET_ID)
- IDX_PN_DIST ON PUBLIC_NOTICE (DIST_ID)
- IDX_PN_STATUS_AUDIT ON PUBLIC_NOTICE (STATUS, AUDIT_ORG_ID)
- IDX_PN_TIME_RANGE ON PUBLIC_NOTICE (START_TIME, END_TIME)
- IDX_PNS_SECT ON PUBLIC_NOTICE_SCOPE (SECT_ID)
- IDX_PNC_COVER ON PUBLIC_NOTICE_COVER (COVER_TYPE, COVER_ID)
- IDX_PNC_NOTICE ON PUBLIC_NOTICE_COVER (NOTICE_ID)
- UNQ_PNR_NOTICE_USER ON PUBLIC_NOTICE_READ (NOTICE_ID, USER_ID)
- IDX_PNR_USER ON PUBLIC_NOTICE_READ (USER_ID)
- IDX_PNR_NOTICE ON PUBLIC_NOTICE_READ (NOTICE_ID)

## Findings
- [MEDIUM] `IDX_PN_STATUS` may overlap with composite `IDX_PN_STATUS_AUDIT` for some query paths.
  - reason: left-prefix access may already cover STATUS-only lookups in many plans.
  - impact: extra write amplification during insert/update on `PUBLIC_NOTICE`.
  - mitigation: keep both initially, then validate with DM8 execution plan and remove redundant one if confirmed.
- [MEDIUM] Multiple single-column regional indexes (`IDX_PN_COMMUNITY`,`IDX_PN_STREET`,`IDX_PN_DIST`) increase maintenance cost.
  - reason: each DML touches more index pages.
  - impact: slower bulk migration writes.
  - mitigation: delay non-critical index creation until after bulk load where feasible.
- [LOW] `IDX_PNR_NOTICE` may be partially covered by unique index `UNQ_PNR_NOTICE_USER` depending query filters.
  - reason: leftmost prefix can satisfy some NOTICE_ID queries.
  - impact: potential index redundancy.
  - mitigation: observe DM8 workload and retain only if hit ratio proves value.
