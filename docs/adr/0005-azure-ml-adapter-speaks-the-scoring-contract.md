# 0005 — The AML adapter speaks the HTTPS scoring contract, not the SDK

**Status:** Accepted

## Context

`packages/detector/aml.py` sits in the request path of every inspection. It
could call an Azure ML managed online endpoint through `azure-ai-ml`, or POST
to the scoring URI directly.

## Decision

POST to the scoring URI. Bearer token from a managed identity scoped to
`https://ml.azure.com/.default`, optional `azureml-model-deployment` header for
a named deployment.

Two reasons. The scoring contract is stable, while SDK convenience surfaces
change between releases. And it keeps `azure-ai-ml` — a large dependency built
for authoring, not inference — out of the request path entirely.

The same reasoning applies to `packages/predictive_models/aml.py`.

## Consequences

- Small dependency footprint on the hot path: `httpx` and `tenacity`.
- The endpoint is treated as an untrusted boundary. Its response is schema-checked before a single value reaches the workflow, and the forecasting adapter **refuses a response missing interval bounds** rather than synthesising them.
- **Endpoint management is not covered.** Creating, updating and scaling the endpoint is the model pipeline's job, not this repository's.
- If the scoring contract changes, this breaks and the SDK would not have.
- Key-based auth is supported because some development endpoints are provisioned that way. It is never the default and is documented as a development affordance.

## What would change this

The SDK gaining something the raw contract cannot express — streaming
inference, or a batch-scoring pattern where the SDK owns meaningful
orchestration.
