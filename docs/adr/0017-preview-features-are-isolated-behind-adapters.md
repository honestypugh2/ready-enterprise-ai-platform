# 0017 — Preview features are isolated behind adapters

**Status:** Accepted

## Context

Preview features are where the interesting capabilities are, and where the
breaking changes are. A repository that uses one in the core makes the whole
thing fragile; a repository that avoids them entirely is out of date on
publication.

## Decision

Every preview or fast-moving dependency sits behind an adapter satisfying a
protocol that a stable implementation also satisfies. The workflow depends on
`Detector`, `Retriever`, `Reasoner` and `Forecaster` — never on a concrete
client.

Optional extras keep preview SDKs out of the default install: `--extra azure`,
`--extra aml`, `--extra onnx`. Absence is a configuration error with a clear
message, not an import traceback at request time.

Preview status is recorded where the decision is made, not only in a register:
`infra/README.md` has a prerequisites table, and `IMPLEMENTATION_STATUS.md`
marks anything preview-dependent.

## Consequences

- A preview change breaks one adapter, not the architecture.
- `make install-all` proves every extra co-resolves — which is how the OpenTelemetry ceiling was found: `azure-monitor-opentelemetry` pins `opentelemetry-sdk<1.44`, so the constraint is capped with an explanatory comment rather than discovered at deploy time.
- **Adapters cost indirection.** Four protocols and four factories exist to make substitution real, which is over-engineering for a system that will only ever use one implementation.
- **Every cloud adapter here is unexecuted.** Isolation protects against preview churn; it does not make an untested adapter work.

## What would change this

Nothing. This is the mechanism that lets the repository use current features
without inheriting their instability.
