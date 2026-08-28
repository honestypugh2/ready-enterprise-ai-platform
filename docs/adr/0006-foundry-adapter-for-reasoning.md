# 0006 — Foundry for reasoning, behind a narrow protocol

**Status:** Accepted

## Context

The reasoning plane produces a grounded natural-language explanation of a
detection, with citations. It needs a model. It must not need anything else.

## Decision

Microsoft Foundry behind the `Reasoner` protocol: `explain(request) ->
Recommendation` and `healthy()`. That is the entire surface.

There is deliberately **no method through which a reasoner could write, approve,
or change an authoritative value**, and `Recommendation` has no field for a
verdict. A contract test asserts both, and asserts that `reasoning` cannot
import `connectors`, `approvals` or `policy_engine`.

## Consequences

- Substituting the model changes wording and cost, not authority.
- `MockReasoner` satisfies the same protocol, so the whole architecture runs offline.
- Grounding is enforced downstream: a non-refusing `Recommendation` must cite at least one retrieved passage, validated by `validate_citations`.
- **The narrow protocol gives up capability.** A reasoner cannot request more evidence, ask a clarifying question, or iterate. Those would need the agent adapter.
- The Foundry adapter is **adapter only** — written against the API, never executed against a deployment. Its real failure modes (verbosity, refusal drift, citation fabrication) are unmeasured.

## What would change this

A workload where the explanation genuinely needs a conversation — the reasoner
must ask the operator something before it can ground an answer.
