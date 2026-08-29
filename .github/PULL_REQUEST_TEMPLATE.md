## What changed, and why

<!-- The problem, not the diff. A reviewer can read the diff. -->

## How it was verified

<!-- Commands actually run, with their results. "Should work" is not a result. -->

```
make check
```

## Checklist

- [ ] `make check` passes (lint, strict types, unit + contract + security suites)
- [ ] `make eval` passes, or a threshold change is justified below
- [ ] Any new claim in the README or docs is enforced by a test, not just written
- [ ] `IMPLEMENTATION_STATUS.md` updated if this changes what exists or what has been proven
- [ ] Nothing newly marked ⬤ Proven unless it was run against the real dependency
- [ ] No fabricated benchmark, price, accuracy figure or customer outcome
- [ ] `make secrets` passes; any new allowlist entry has a stated reason

### If this touches a governance control

<!-- Policy engine, approvals, the scoped writer, audit, entitlements, redaction. -->

- [ ] A test asserts the control still refuses the case it exists to refuse
- [ ] The refusal is recorded in the audit trail, not only logged
- [ ] `tests/contract/` still enforces the plane boundary and the sole writer

### If this touches infrastructure

- [ ] `make infra-lint` passes
- [ ] The what-if preview on this pull request has been read
- [ ] No secret introduced; every dependency reached by managed identity
