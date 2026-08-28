# 0007 — Routing is a versioned policy, not a heuristic

**Status:** Accepted

## Context

"Use the small model unless the task is hard" is the routing rule most systems
actually implement, in an `if` statement, with no record of why a given request
went where it went.

## Decision

Routing is `packages/model_router/policies/routing.yaml`: a versioned,
hash-identified document listing candidate routes with their task support,
capabilities, cost category, latency target, maximum classification and
evaluation reference.

Every `RouteDecision` records the selected route, the reason codes, **and the
excluded candidates with their exclusion reasons**.

## Consequences

- "Why did this use the frontier model?" is answerable from the audit trail rather than by reading code.
- Deterministic and rules-engine routes are first-class `RouteKind` values, so the router can decide that no model is needed at all.
- A route with no evaluation reference is selectable only when the policy explicitly permits unproven routes.
- **The cost and latency attributes are declared, not measured.** They are placeholders until a live environment fills them in, and `IMPLEMENTATION_STATUS.md` says so.
- Route health probing is stubbed.
- A YAML policy is more indirection than an `if`, and for two routes that is arguably over-engineering.

## What would change this

If routing decisions became genuinely dynamic — chosen from live latency and
error rates rather than declared properties — the policy becomes a set of
constraints on a controller rather than the decision itself.
