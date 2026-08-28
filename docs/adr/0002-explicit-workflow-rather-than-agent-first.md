# 0002 — An explicit workflow, with agency added only where it earns its cost

**Status:** Accepted

## Context

The obvious way to build this in 2026 is an agent with tools: give a model the
detector, the index and the ERP connector, and let it decide the sequence.

For this workload the sequence is known. A frame is inspected, evidence is
retrieved, policy decides, a human approves, a record is written. That control
flow can be drawn as a diagram — and a control flow that can be drawn does not
need to be discovered at run time, on every request, at the cost of a model
call per decision.

## Decision

Implement twelve explicit steps in `packages/workflows/quality_workflow.py`.

Keep `BoundedAgentAdapter` for cases where tool selection is genuinely dynamic,
with a step budget, a fixed tool set and the same approval gate.

## Consequences

- Cheaper: one reasoning call per transaction rather than one per decision.
- Faster: no planning latency.
- Testable: 273 tests can assert the path, because there is a path.
- Auditable: the audit chain has the same twelve step names every time, so a reviewer compares like with like.
- **Less flexible.** A new step requires a code change and a deployment. An agent would have adapted without one.
- The repository is therefore *not* a demonstration of agent frameworks, and cannot be used as one.

This is the decision most likely to be argued with, and the argument is
legitimate: for a workload whose steps genuinely vary per request, this is the
wrong shape.

## What would change this

Step variance. If the same workload started needing materially different
sequences per request — different evidence sources, conditional sub-workflows,
recovery paths that cannot be enumerated — the explicit workflow becomes a
growing conditional and the agent adapter becomes the better default.
