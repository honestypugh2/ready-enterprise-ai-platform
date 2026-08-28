# 0004 — Local mock mode is the enforced default

**Status:** Accepted

## Context

Reference architectures are usually unrunnable. They need a subscription, a
model deployment, a search index and an hour of provisioning before anyone can
see what they claim. Most readers never get there, and the claims stay
unverified.

A demo also has to survive a conference network.

## Decision

`local_mock` is the default execution mode, and it is **enforced rather than
documented**. The settings validator in `packages/platform_config/settings.py`
raises if local mode is configured with a cloud provider, or with
`dry_run=false`. `ScopedWriter` evaluates `request.dry_run or dry_run_default`,
so a caller cannot override the default downward.

## Consequences

- `make install && make check && make demo` works on a clean clone with no Azure account, and produces the same result on every machine.
- Every claim in the README is re-verifiable by a reader who does not trust it.
- The test suite is deterministic: no network, no wall clock, no seed the test does not control.
- **The mock components are fixtures with no quality claim.** The mock detector is hash-seeded; the mock reasoner is a template engine; the local retriever uses hashed character trigrams, not semantic embeddings.
- **Passing locally proves the governance path, not the AI quality.** Both statements are in `IMPLEMENTATION_STATUS.md`, and the demo UI labels every figure as a fixture or a measurement.

## What would change this

Nothing foreseeable. If the mocks ever became good enough to be mistaken for
measurements, that would be a reason to make them *worse* and more obviously
synthetic, not to remove the mode.
