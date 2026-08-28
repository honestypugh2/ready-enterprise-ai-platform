# Reuse and attribution

This repository integrates patterns from four MIT-licensed repositories. Every
one is credited here and, where a specific file adapts a specific pattern, in
that file.

Nothing was copied verbatim. What was reused is *design*: the shape of a
solution someone had already worked out.

## Sources

### [foundry-workload-studio](https://github.com/honestypugh2/foundry-workload-studio) — MIT

A production-minded Foundry accelerator showing one governed platform powering
multiple business-aligned workloads.

**Reused:** the subscription-scoped Bicep layout, the `modules/` +
`environments/` split with one parameter file per environment, and the
WAF-aligned posture that varies SKU, retention and network access by
environment rather than by a separate template.

**Where:** `infra/main.bicep`, `infra/modules/`, `infra/environments/`.

**Not reused:** the multi-workload registry and the Explorer UI. This repository
demonstrates one workload deeply rather than four broadly.

### [wordpress-chatbot](https://github.com/honestypugh2/wordpress-chatbot) — MIT

A Foundry chatbot for a county-government scenario, whose `ai_demo/` directory
works out per-user cost attribution through the APIM AI Gateway.

**Reused:** the identity-precedence chain (Entra `oid` › `x-user-id` ›
subscription id) and its security reasoning — that `x-user-id` is safe only
when set by a trusted server-side component; per-user token limiting keyed on
the resolved identity; `azure-openai-emit-token-metric` with attribution
dimensions; and the shape of the chargeback KQL.

The justifying argument is reused directly, because it is correct: *the gateway
is the single hop that sees both the caller identity and the model's token
usage, and the caller cannot tamper with what it emits. App-side logging is
best-effort and spoofable; gateway-side logging is authoritative.*

**Where:** `infra/apim/ai-gateway.policy.xml`,
`infra/monitor/queries/cost-per-completed-task.kql`,
[ADR-0012](../adr/0012-apim-as-the-ai-gateway.md).

**Extended:** a `CorrelationId` dimension, so cost attributes to a *transaction*
and not only to a user — which is what makes cost per completed task
computable. Semantic caching is deliberately left off; see the policy comment.

### [warehouse-replenishment-ai-demo](https://github.com/honestypugh2/warehouse-replenishment-ai-demo) — MIT

Governed, human-in-the-loop warehouse replenishment with Copilot Studio,
Foundry, Databricks and D365. The closest architectural sibling to this
repository.

**Reused:** the governance spine, which that repository had already worked out
correctly —

- a deterministic validator ahead of reasoning, blocking on a rule rather than leaving it to the model
- **one component permitted to mutate the system of record**, and only after explicit human approval
- citations on every recommendation, with recommended values never fabricated by the reasoner
- an audit id returned for every approved write
- a mock-first default that runs fully offline

**Where:** the whole governance path — `packages/policy_engine`,
`packages/approvals`, `packages/connectors/writer.py`, `packages/audit`.

**Extended:** that repository states "writer is the only agent allowed to mutate
D365" as a design property. Here it is a **build-failing contract test** that
reads the import graph, plus six named refusals whose order is asserted from
source. The claim is the same; the enforcement is the addition.

### [foundry-copilot-hr-policy-knowledge](https://github.com/honestypugh2/foundry-copilot-hr-policy-knowledge) — MIT

Five retrieval patterns compared with committed evidence, published alongside a
Microsoft Tech Community article.

**Reused:** the uv project shape; the retrieval-pattern taxonomy that separates
direct index, agentic retrieval and force-grounded synthesis; the two-phase
provision-then-deploy discipline that verifies identity permissions before
activating private images; and the disclosure convention — a prominent,
unambiguous statement that a repository is a learning accelerator and not
production-ready.

**Where:** `pyproject.toml`, `packages/retrieval/`,
`IMPLEMENTATION_STATUS.md`, `scripts/deploy.sh`.

**Not reused:** Copilot Studio integration and the benchmark workbench.

## Not referenced

`foundry-copilot-search-validate` is deliberately not referenced.

## Obligations

All four sources are MIT-licensed, which requires the copyright notice and
permission notice be preserved in substantial portions of the software. Since
nothing here is a substantial verbatim portion, the obligation is met by
attribution — this document, plus the in-file notes.

This repository is also MIT-licensed. See [LICENSE](../../LICENSE).

## External dependencies

Third-party dependencies are declared in `pyproject.toml` and
`apps/web/package.json`. `make sbom` generates a CycloneDX SBOM, and
`.github/workflows/security.yml` publishes one on every push to `main`.
