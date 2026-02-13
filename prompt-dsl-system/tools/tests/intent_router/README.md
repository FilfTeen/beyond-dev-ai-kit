# Intent Router Test Suite

Canonical location for intent routing verification.

## Files

- `test_intent_router.py`: regression + invariants + boundary gating
- `intent_router_pressure.py`: deterministic high-pressure checks
- `testdata/intent_router_cases.v1.json`: versioned regression fixtures

## Run

```bash
/usr/bin/python3 -m unittest -v prompt-dsl-system/tools/tests/intent_router/test_intent_router.py
/usr/bin/python3 prompt-dsl-system/tools/tests/intent_router/intent_router_pressure.py --repo-root . --single-calls 6000 --concurrent-calls 8000 --concurrency 32 --max-p99-ms 8
```

This suite is the only supported entry for intent-router regression/pressure tests.
