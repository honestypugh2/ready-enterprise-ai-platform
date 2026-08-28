# 0019 — READY AI is an original field framework, not a Microsoft standard

**Status:** Accepted

## Context

`packages/readyai` scores a workload across five weighted dimensions and
produces a release gate and a remediation backlog. It is presented in a session
delivered by a Microsoft employee, using Microsoft products, in a repository
that deploys Microsoft services.

That combination invites the audience to hear it as official guidance.

## Decision

READY AI is labelled an **original field framework** created for the *Beyond
the Agent* session, not a Microsoft standard, product or official guidance —
every time it appears: in the package docstring, in the CLI output, in the API
response (`/v1/governance/readyai` returns a `notice` field), in the README, and
in `CONTRIBUTING.md` as a standing constraint.

The reference implementation is scored honestly and **fails its own release
gate**. That result is left visible.

## Consequences

- A practitioner can adopt, fork or reject it on its merits.
- Evidence is required above the lowest maturity level, enforced by a validator — a claim without an artifact scores at the level below, which is what stops the scorecard measuring optimism.
- **A visible failing gate looks bad in a demo.** It is the honest result: the repository has no authentication, no durable approval store and no deployed environment, and a framework its own author's code passes trivially would be worth nothing.
- The labelling is repetitive on purpose. One disclaimer in a README does not survive a screenshot.

## What would change this

If it were ever adopted as official guidance, the labelling would change — and
that decision would not be this repository's to make.
