# Preview and version-sensitive dependency register

Every dependency here that is preview, prerelease, version-pinned or otherwise
liable to change under the repository. One page, because the alternative is a
reader discovering each constraint separately at the moment it breaks.

**Rule:** a preview dependency may be used, but it must sit behind an adapter
that a stable implementation also satisfies. A preview change should break one
adapter, not the architecture.

**Last reviewed:** 2026-10-01

---

## 1. Azure resource API versions

Preview API versions in `infra/`. Everything not listed is on a GA version.

| Resource type | API version | Why preview | Blast radius if it changes |
|---|---|---|---|
| `Microsoft.Insights/diagnosticSettings` | `2021-05-01-preview` | The stable line does not expose `categoryGroup`, which is what keeps the diagnostic settings terse instead of enumerating every category | Every module that emits diagnostics — 8 call sites. Recoverable by enumerating categories explicitly |

**API Management is on GA `2024-05-01`.** It was previously on
`2024-06-01-preview` on the belief that the AI Gateway policies needed the
preview surface. They do not: `llm-token-limit` and `llm-emit-token-metric` are
policy XML, stored through the ordinary policy resource, and backend circuit
breakers are GA. `tests/contract/test_ai_gateway_policy.py` fails if an API
Management resource leaves GA without a row in this table.

**Action when one of these goes GA:** move to the GA version and re-run
`make infra-lint`.

## 2. Evolving GA surfaces

GA, but young enough that properties are still being added.

| Resource | Version | Watch |
|---|---|---|
| `Microsoft.CognitiveServices/accounts/projects` | `2025-06-01` | Foundry projects are a recent addition. Verify the version is available in your subscription's registered providers before deploying |
| `Microsoft.App/managedEnvironments` | `2025-01-01` | `vnetConfiguration.internal` semantics have changed across versions; the internal-only path is untested here |
| `Microsoft.Search/searchServices` | `2025-05-01` | `semanticSearch` tiers and `disableLocalAuth` are both relatively recent |

## 3. Python dependency constraints

| Constraint | Where | Reason | What breaks if raised blindly |
|---|---|---|---|
| `opentelemetry-api>=1.44.0,<1.45` | `pyproject.toml` | `azure-monitor-opentelemetry` pins the SDK to a single minor line (1.8.10 requires 1.44) | The `azure` extra fails to resolve. Found by `make install-all`, which exists to catch exactly this |
| `opentelemetry-sdk>=1.44.0,<1.45` | `pyproject.toml` | Same | Same |
| `opentelemetry-instrumentation-fastapi>=0.65b0,<0.66` | `pyproject.toml` | Instrumentation ships on a **beta version line** by upstream convention. The explicit prerelease bound is what lets the resolver accept it without globally enabling prereleases | Enabling prereleases globally would pull beta versions of unrelated packages |
| `opentelemetry-instrumentation-httpx>=0.65b0,<0.66` | `pyproject.toml` | Same | Same |

Raise these bounds by hand, together with `azure-monitor-opentelemetry`, and
confirm with `make install-all`. The ceiling and the exporter move together,
deliberately.

## 4. Optional extras

Preview and heavyweight SDKs are kept out of the default install. Absence is a
configuration error with a clear message, never an import traceback at request
time.

| Extra | Contains | Needed for |
|---|---|---|
| `azure` | `azure-identity`, `azure-keyvault-secrets`, `azure-search-documents`, `azure-servicebus`, `azure-monitor-opentelemetry`, `openai` | Any non-local execution mode |
| `aml` | `azure-ai-ml` | Authoring against Azure ML. **Not** used in the request path — the detector adapter speaks the HTTPS scoring contract directly |
| `onnx` | `onnxruntime`, `numpy`, `pillow` | Locally executed ONNX detection |
| `dev` | pytest, ruff, mypy, bandit, pip-audit, respx | Development only |

`make install-all` installs every extra together, which proves they co-resolve.
That target is how the OpenTelemetry ceiling was discovered, rather than at
deploy time.

## 5. Prerequisites that are not version constraints

Things that will block a deployment for reasons unrelated to a version number.

| Item | Constraint | Consequence |
|---|---|---|
| **Entra app registration** | The gateway's `entra-audience` named value requires an Application ID URI. APIM resolves named values **at apply time**, so `apim.bicep` composes the JWT branch into the policy only when both Entra values are supplied | Until then the policy applies without it and budgets each caller by its APIM subscription. `x-user-id` is honoured **only** from a subscription listed in `trustedProxySubscriptionIds` (empty by default), i.e. a server-side component that validated its own session. Frequently the deploying subscription does not grant app-registration privileges |
| **Gateway content safety** | `llm-content-safety` requires its backend's authorization credentials to be the gateway's managed identity. Microsoft documents this only as a portal step; no ARM API version, GA or preview through `2025-09-01-preview`, exposes the property | `enableContentSafety` defaults to `false`. When enabled, Bicep creates the backend, named value, role and policy block; the credential is set by hand as described in `infra/README.md`. Until then moderated requests fail closed |
| **APIM tier** | `Internal` VNet mode is **Premium only** | With private networking on a lower tier the gateway stays `External`. `infra/modules/apim.bicep` does this rather than failing, and the behaviour is stated here rather than discovered |
| **APIM provisioning time** | Developer tier takes roughly 45 minutes | `deployApiGateway` defaults to `false` outside prod for this reason |
| **AML online endpoint** | Not provisioned by this repository | An endpoint without a registered model deploys an empty shell that reports healthy and scores nothing, which is worse than its absence. Deploy it from the model's own pipeline |
| **Private networking reachability** | Prod disables public access on every resource | You need a jump host, VPN or ExpressRoute to reach anything — including to run `reap doctor` |
| **ACR pull at revision start** | Container Apps must reach the registry when a revision starts | Verify the managed identity holds `AcrPull` **before** switching to a private image, or the revision fails to start with a misleading error. This is why `azure.yaml` is two-phase |

## 6. AI Gateway capabilities

Every current API Management AI Gateway capability, and what this repository
does with it. Reviewed against Microsoft Learn on the date above. A capability
marked *not applicable* gains an implementation when a caller for it exists,
not before.

| Capability | Microsoft status | Here | Why |
|---|---|---|---|
| `llm-token-limit` | GA | Adopted | Per-caller budget keyed on the resolved identity |
| `llm-emit-token-metric` | GA | Adopted, bounded dimensions only | Per-user and per-transaction attribution comes from logged headers; see `docs/architecture/reuse-and-attribution.md` |
| Backend circuit breaker with `Retry-After` | GA | Adopted, server faults only | One backend serves every deployment, so a 429-triggered trip would let one caller cut off all of them. Throttling is left to `llm-token-limit` and the deployment's own `Retry-After` |
| `llm-content-safety` | GA | Opt-in, off by default | Needs one portal step; see section 5 |
| API diagnostic `metrics: true` to Application Insights | GA | Adopted | Required for token metrics to publish. Bodies are never logged |
| LLM prompt and completion logging (`largeLanguageModel` diagnostic) | Preview ARM only | **Not adopted** | Prompts and completions carry entitlement-scoped evidence. Token usage is logged without it |
| Backend pool (round-robin, weighted, priority, session-aware) | GA | Not applicable | One model endpoint. Add a pool when a second independently deployable endpoint exists, with a failure-injection test |
| `llm-semantic-cache-lookup` / `-store` | GA | **Deliberately excluded** | A hit returns evidence retrieved under another caller's entitlement. A contract test fails if it appears on this route |
| Responses API, Realtime API, provider passthrough routes | GA | Not applicable | The reasoning adapter calls Chat Completions only |
| Anthropic Messages, Google Vertex AI model APIs | GA (Anthropic on v2 tiers) | Not applicable | No such backend |
| MCP servers (expose REST as MCP, or proxy an existing one) | GA on dedicated tiers; tools only, no resources or prompts; not in workspaces | Not applicable | The platform exposes no tools to agents. Adopting it needs OAuth, per-tool authorization, quotas and tool-input validation first |
| A2A agent APIs | GA on dedicated tiers; JSON-RPC only | Not applicable | The platform exposes no agent |
| Unified model API | **Preview** | Not adopted | Single provider. Fails acceptance gate 1 below until a second provider exists |
| AI Gateway in Microsoft Foundry | **Preview** | Not adopted | Governance stays in reviewable policy XML, not a portal |
| AI Gateway early release channel | Early access | **Never in production** | Use a dedicated non-production instance if early validation is wanted |

### Acceptance gates for an AI Gateway preview

A preview capability is adopted only when all of these hold:

1. A workload in this repository needs it, and no GA capability meets that need.
2. Microsoft documents it publicly, for the deployed tier and region.
3. It sits behind a parameter that defaults to off, with a GA fallback.
4. It is on the lowest preview API version that exposes the property — never
   simply the newest — with a row in section 1.
5. A contract test covers its configuration and an integration test covers
   rollback to the GA path.

## 7. Frontend

| Package | Version | Note |
|---|---|---|
| `react`, `react-dom` | `^19.2.8` | Current major |
| `vite` | `^8.2.2` | Moved from 7 during the build; 8 is current |
| `eslint` | `^10.9.1` | Moved from 9 after npm warned that 9 is no longer supported |
| `vitest` | `^3.2.4` | Current |

GitHub Dependabot alerts flag undici, brace-expansion and vitest advisories
that the last local `npm audit` did not. Routine
upgrades are manual: Dependabot version and security updates are off during
development. Dependabot alerts are on.

## 8. What this register does not cover

- **Model deployment versions.** `infra/modules/foundry.bicep` pins model versions with `versionUpgradeOption: NoAutoUpgrade`, because a model that upgrades itself invalidates every evaluation result recorded against it. Changing a pinned model version is an evaluation-gate event, not a dependency update.
- **The policy document version.** Governed separately; every decision records the version and file hash.
- **What has actually been deployed and observed.** That is recorded, per capability, in [IMPLEMENTATION_STATUS.md](../../IMPLEMENTATION_STATUS.md). Constraints here are predictions unless that file says otherwise.

## Review cadence

Re-read this page when any of these happens:

1. `make install-all` fails to resolve
2. `make infra-lint` reports a schema error on a preview type
3. A dependency upgrade touches a pinned constraint
4. Before the first deployment to any new subscription
