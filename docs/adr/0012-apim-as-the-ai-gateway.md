# 0012 — API Management is the AI Gateway

**Status:** Accepted

## Context

Token budgets and cost attribution can live in the application. The application
is also the component with an incentive to under-report and the ability to be
compromised.

## Decision

APIM sits between the platform and Foundry. It resolves the caller identity
(Entra `oid` › `x-user-id` › subscription id), applies a per-user token limit
keyed on that identity, and emits `azure-openai-emit-token-metric` with
`UserId`, `WorkloadId`, `CorrelationId` and `ModelDeployment` dimensions.

The gateway is the single hop that sees both the caller identity and the
model's token usage, and the caller cannot tamper with what it emits. App-side
logging is best-effort and spoofable; gateway-side logging is authoritative.

## Consequences

- The token budget is one the application cannot raise for itself.
- Chargeback and showback queries have a trustworthy source.
- Backend authentication is a managed identity; no key appears in the policy, in a named value, or in any request.
- Upstream headers naming the deployment, region and rate limits are stripped on the way out.
- **Semantic caching is deliberately off.** A cache hit on a governed explanation can return evidence retrieved for a different transaction under a different entitlement. It is enabled per route, only where responses carry no entitlement-scoped content.
- **The Entra path requires an app registration** for `entra-audience`. APIM resolves named values at apply time, so the policy can only be applied after they exist — and app-registration privileges are frequently not granted in the subscription doing the deploying. Until then attribution is header and subscription based, which is weaker.
- APIM Developer tier takes roughly 45 minutes to provision, so the gateway is off by default outside prod.
- `Internal` VNet mode is **Premium only**. On a lower tier with private networking the gateway stays `External`.

## What would change this

Nothing for the multi-consumer case. For a single-tenant workload with one
caller, the gateway is real cost for attribution nobody needs.

Adapted from the per-user cost attribution pattern in
[honestypugh2/wordpress-chatbot](https://github.com/honestypugh2/wordpress-chatbot).
