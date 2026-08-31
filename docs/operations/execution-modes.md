# Execution modes

Three modes. The mode is always visible — in `/healthz`, in every API response,
in the CLI output, and on every screen of the demo UI. A demonstration that does
not name its mode invites the audience to assume the wrong one.

| | `local_mock` | `azure_dev` | `production` |
|---|---|---|---|
| Detector | Hash-seeded fixture | AML endpoint | AML endpoint |
| Retrieval | Local corpus, lexical trigrams | Azure AI Search | Azure AI Search |
| Reasoning | Template engine | Foundry | Foundry |
| Connector | In-memory | In-memory or real | Real |
| Writes | **Always dry run** | Configurable | Configurable |
| Telemetry | stdout | App Insights | App Insights |
| Credentials | **None** | Managed identity | Managed identity |
| Network | **None required** | Required | Required |

## `local_mock` — the enforced default

The default, and it is **enforced rather than documented**. The settings
validator raises if local mode is configured with a cloud provider, or with
`dry_run=false`:

```
local_mock mode cannot use detector provider 'aml';
set REAP_MODE=azure_dev to reach cloud dependencies
```

`ScopedWriter` evaluates `request.dry_run or self._dry_run_default`, so a caller
passing `dry_run=False` **cannot override the configured default downward**. An
integration test asserts exactly this.

Everything works offline: `make install && make check && make demo` on a clean
clone, with no Azure account, producing the same result on every machine.

**What this mode does not prove.** The mock detector is a fixture; the mock
reasoner is a template engine; the local retriever uses hashed character
trigrams, not semantic embeddings. Passing locally proves the **governance
path**, not the AI quality. See
[the model card](../architecture/model-cards/mock-detector.md).

## `azure_dev`

Real Azure dependencies, non-production data, writes still simulated by default.
Requires `az login` or a managed identity; `DefaultAzureCredential` resolves to
the developer's own signed-in identity locally.

This is the first mode where the adapters are actually executed. Everything
marked **Adapter only** in `IMPLEMENTATION_STATUS.md` is unproven until it runs
here.

## `production`

Refuses to start without App Insights, a Search endpoint and a reasoning
endpoint:

```
production mode requires: REAP_OTEL_APPLICATIONINSIGHTS_CONNECTION_STRING,
REAP_RETRIEVAL_SEARCH_ENDPOINT, REAP_REASONING_ENDPOINT
```

A missing telemetry destination is not a degraded mode — it is a workload whose
first failures are invisible.

Public network access is disabled on every resource, so private networking is
**derived** rather than requested. Reaching a production environment requires a
jump host, VPN or ExpressRoute.

## Switching

```bash
REAP_MODE=azure_dev
REAP_DETECTOR_PROVIDER=aml
REAP_DETECTOR_AML_ENDPOINT_URL=https://<endpoint>.<region>.inference.ml.azure.com/score
REAP_RETRIEVAL_PROVIDER=azure_search
REAP_RETRIEVAL_SEARCH_ENDPOINT=https://<search>.search.windows.net
REAP_REASONING_PROVIDER=foundry
REAP_REASONING_ENDPOINT=https://<foundry>.services.ai.azure.com/
```

No code change. That substitutability is the point of the plane structure:
version-sensitive dependencies stay behind contracts that stable local
implementations also satisfy.

Verify with `reap doctor`, which reports the mode, each plane's health, the
policy version and hash, the dry-run state and the kill switch.

## The kill switch

`REAP_GOVERNANCE_KILL_SWITCH_ENGAGED=true` stops the workload **before
inference**, so it spends nothing. It halts, records the halt in the audit
trail, and is not retryable — retrying past an administrative stop defeats the
point of it.

It is the control an operations team asks for in the first review, and it has to
work without a deployment.
