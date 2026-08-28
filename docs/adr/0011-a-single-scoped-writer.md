# 0011 — Exactly one component may mutate a system of record

**Status:** Accepted

## Context

This is the strongest claim the architecture makes: a compromised or merely
mistaken reasoning path cannot cause a write. A claim that strong has to be
enforced structurally, because a convention holds only until someone is in a
hurry.

## Decision

`connectors.writer.ScopedWriter` is the only component that may call a
connector. `execute()` performs six refusals, in order, before anything changes:

1. Policy allowed this transaction.
2. The action kind is in the permitted set.
3. The approval verifies against this proposal fingerprint and policy decision.
4. The connector supports the action.
5. The idempotency key has not already been applied.
6. Dry run is off.

`ActionRequest` requires `approval_id`, `proposal_fingerprint`,
`policy_decision_id` and `idempotency_key`, so an unbound write **cannot be
expressed**, and `dry_run` defaults to `True`.

`tests/contract/test_sole_writer.py` parses the import graph and fails the build
if any module outside an explicit permitted set acquires a path to a connector.
It also uses `inspect.getsource` to assert that `verify_for_write` appears
before `_attempt_write` — a check after the write is a log entry, not a control.

## Consequences

- The claim is falsifiable and is checked on every commit.
- Adding a write path means routing it through the writer, not adding an exemption. `CONTRIBUTING.md` says a change that adds an exemption will be declined.
- Idempotency is keyed on the policy decision, so retrying the same decision cannot produce a second work order.
- Compensation is explicit and gets its own receipt, because distributed transactions do not exist across an ERP boundary.
- **All three connectors are in-memory.** The authorization chain transfers; the integration — auth, throttling, schema drift, partial failure — is entirely unbuilt.
- **A single writer is a bottleneck and a single point of failure.** At volume it needs to be a horizontally scaled service, which changes the idempotency store from in-process to shared.

## What would change this

Nothing. If this stops being true the architecture's central claim is false.
