# 0014 — Evaluation gates block a release

**Status:** Accepted

## Context

Evaluation that produces a dashboard nobody reads is theatre. Evaluation that
blocks a merge is a control.

## Decision

`packages/evaluation` runs 16 cases through the **real workflow**, not a stub,
and grades them with nine graders of which seven are blocking: entitlement
compliance, policy compliance, safety, action correctness, refusal, retrieval
relevance and citation precision.

`make eval` exits non-zero when a blocking grader falls below its threshold.
`.github/workflows/eval.yml` runs it as its own status check, separate from
`ci.yml`, because "tests pass" and "the model behaves acceptably" are different
claims and one green tick hides which failed.

## Consequences

- The number that gates a release and the number a dashboard reports come from the same code. A harness that grades a mock grades the mock.
- Governance regressions block a merge rather than surfacing in a demo.
- Running the real workflow surfaced defects inspection had missed, including a payload field populated from the wrong source.
- **The current scores describe the harness, not a model.** They are measured against a deterministic mock reasoner and a lexical retriever. Every threshold must be re-baselined after the first live run, and the PR comment says so on every run.
- Sixteen cases is small. It covers the governance matrix, not the input space.
- A blocking gate creates pressure to lower a threshold to unblock a release. `CONTRIBUTING.md` requires a threshold change to be justified in the pull request.

## What would change this

Nothing. If a threshold is wrong, change the threshold deliberately and record
why — do not remove the gate.
