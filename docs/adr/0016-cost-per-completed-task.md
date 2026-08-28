# 0016 — Cost per completed task, and no invented prices

**Status:** Accepted

## Context

Cost per call flatters a system that retries. Cost per token flatters a system
that answers briefly and wrongly. Neither compares against the manual process
the workload replaced.

Reference architectures also routinely quote prices, which are wrong by region,
by tier, by commitment and by the customer's negotiated rate.

## Decision

`packages/cost_attribution` records units, token counts and consumption
surfaces per correlation id, and computes **cost per completed task**.

`CostLedger.summarise()` **refuses to produce a currency figure without a
supplied rate card.** `CostSummary.estimated_total` is `None` and `currency` is
`UNSPECIFIED` until the caller provides rates.

`frontier_calls_avoided` is counted, so routing to a cheaper model is visible
as a saving rather than asserted as one.

## Consequences

- The unit economics figure is comparable against a business process.
- Completion rate falls out of the same measurement, and the cost of work the platform started and did not finish becomes visible.
- **No price appears anywhere in this repository**, and the demo says so on screen: "No rate card supplied, so no currency figure is claimed."
- **The token counts are fictional** — they come from the mock reasoner. The method is sound; every number it currently produces is a demonstration.
- Attributing to a completed task requires correlation ids to survive every hop, which the gateway policy and the KQL both depend on.

## What would change this

Nothing. The refusal to invent a price is the point.
