# 0010 — Human approval happens in a separate request from the write

**Status:** Accepted

## Context

The easy implementation blocks: propose, wait for a decision, write — all in
one request. It is simpler, and it makes the approval a formality, because the
state that justified the proposal is assumed still true when the write happens.

## Decision

`GovernedQualityWorkflow.run()` executes steps 1–8 and stops at the gate.
`complete()` executes steps 9–12 after a decision arrives, and **re-validates**:
the approval must still exist, still permit a write, not have expired, and
still bind to this exact proposal fingerprint and policy decision id.

The approval surface carries evidence as data — citations, authoritative
values, reason codes, the expected downstream effect — not only a summary
sentence. An approver asked to click "approve" on a sentence is a rubber stamp
with a name attached.

## Consequences

- No held connection, no long-lived transaction.
- The write cannot proceed on stale authorisation, because the check happens at write time and not at approval time.
- Separation of duties, role match, expiry and dual control are all enforced. Dual control requires **two distinct principals** — one person deciding twice does not satisfy it, and a test asserts it.
- The proposal and the write are one audit chain, via `AuditTrailBuilder.resume`.
- **Two requests means state must persist between them.** In this repository that state is a module-level dictionary and an in-memory approval store. It does not survive a restart and is not shared across replicas. **This is gap #1 in `IMPLEMENTATION_STATUS.md`.**
- Approval latency becomes a metric that determines whether the workload is viable at all. `infra/monitor/queries/approval-latency.kql` measures it.

## What would change this

Nothing about the separation. The storage must change before any pilot.
