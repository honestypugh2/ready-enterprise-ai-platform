# Preview and version-sensitive dependency register

Every dependency here that is preview, prerelease, version-pinned or otherwise
liable to change under the repository. One page, because the alternative is a
reader discovering each constraint separately at the moment it breaks.

**Rule:** a preview dependency may be used, but it must sit behind an adapter
that a stable implementation also satisfies. A preview change should break one
adapter, not the architecture.

**Last reviewed:** 2026-08-29

---

## 1. Azure resource API versions

Preview API versions in `infra/`. Everything not listed is on a GA version.

| Resource type | API version | Why preview | Blast radius if it changes |
|---|---|---|---|
| `Microsoft.ApiManagement/service` | `2024-06-01-preview` | The AI Gateway policies (`azure-openai-token-limit`, `azure-openai-emit-token-metric`) are only expressible on the preview surface | `infra/modules/apim.bicep` fails to compile. The gateway is optional outside prod (`deployApiGateway=false`), so dev and test are unaffected |
| `Microsoft.ApiManagement/service/apis` | `2024-06-01-preview` | Same | Same module |
| `Microsoft.ApiManagement/service/apis/policies` | `2024-06-01-preview` | Same | Same module |
| `Microsoft.ApiManagement/service/apis/operations` | `2024-06-01-preview` | Same | Same module |
| `Microsoft.ApiManagement/service/backends` | `2024-06-01-preview` | Same | Same module |
| `Microsoft.ApiManagement/service/namedValues` | `2024-06-01-preview` | Same | Same module |
| `Microsoft.ApiManagement/service/loggers` | `2024-06-01-preview` | Same | Same module |
| `Microsoft.Insights/diagnosticSettings` | `2021-05-01-preview` | The stable line does not expose `categoryGroup`, which is what keeps the diagnostic settings terse instead of enumerating every category | Every module that emits diagnostics — 8 call sites. Recoverable by enumerating categories explicitly |

**Action when one of these goes GA:** move to the GA version and re-run
`make infra-lint`. The APIM policy XML is unaffected; only the ARM surface
changes.

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
| `opentelemetry-api>=1.43.0,<1.44` | `pyproject.toml` | `azure-monitor-opentelemetry` pins the SDK to a single minor line | The `azure` extra fails to resolve. Found by `make install-all`, which exists to catch exactly this |
| `opentelemetry-sdk>=1.43.0,<1.44` | `pyproject.toml` | Same | Same |
| `opentelemetry-instrumentation-fastapi>=0.64b0,<0.65` | `pyproject.toml` | Instrumentation ships on a **beta version line** by upstream convention. The explicit prerelease bound is what lets the resolver accept it without globally enabling prereleases | Enabling prereleases globally would pull beta versions of unrelated packages |
| `opentelemetry-instrumentation-httpx>=0.64b0,<0.65` | `pyproject.toml` | Same | Same |

`.github/dependabot.yml` ignores minor updates to `opentelemetry-*` for this
reason. The ceiling and the exporter move together, deliberately.

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
| **Entra app registration** | The gateway's `entra-audience` named value requires an Application ID URI. APIM resolves named values **at apply time**, so the policy cannot be applied before the named values exist | Until then the gateway attributes cost by header and subscription id, which is weaker and spoofable. The `x-user-id` path is safe **only** when set by a trusted server-side component. Frequently the deploying subscription does not grant app-registration privileges |
| **APIM tier** | `Internal` VNet mode is **Premium only** | With private networking on a lower tier the gateway stays `External`. `infra/modules/apim.bicep` does this rather than failing, and the behaviour is stated here rather than discovered |
| **APIM provisioning time** | Developer tier takes roughly 45 minutes | `deployApiGateway` defaults to `false` outside prod for this reason |
| **AML online endpoint** | Not provisioned by this repository | An endpoint without a registered model deploys an empty shell that reports healthy and scores nothing, which is worse than its absence. Deploy it from the model's own pipeline |
| **Private networking reachability** | Prod disables public access on every resource | You need a jump host, VPN or ExpressRoute to reach anything — including to run `reap doctor` |
| **ACR pull at revision start** | Container Apps must reach the registry when a revision starts | Verify the managed identity holds `AcrPull` **before** switching to a private image, or the revision fails to start with a misleading error. This is why `azure.yaml` is two-phase |

## 6. Frontend

| Package | Version | Note |
|---|---|---|
| `react`, `react-dom` | `^19.2.8` | Current major |
| `vite` | `^8.2.2` | Moved from 7 during the build; 8 is current |
| `eslint` | `^10.9.1` | Moved from 9 after npm warned that 9 is no longer supported |
| `vitest` | `^3.2.4` | Current |

`npm audit` reports zero vulnerabilities as of the last review. Dependabot
groups minor and patch updates weekly.

## 7. What this register does not cover

- **Model deployment versions.** `infra/modules/foundry.bicep` pins model versions with `versionUpgradeOption: NoAutoUpgrade`, because a model that upgrades itself invalidates every evaluation result recorded against it. Changing a pinned model version is an evaluation-gate event, not a dependency update.
- **The policy document version.** Governed separately; every decision records the version and file hash.
- **Anything that has actually been deployed.** Nothing has. Every constraint above is a prediction about what will happen, not an observation — see [IMPLEMENTATION_STATUS.md](../../IMPLEMENTATION_STATUS.md).

## Review cadence

Re-read this page when any of these happens:

1. `make install-all` fails to resolve
2. `make infra-lint` reports a schema error on a preview type
3. Dependabot opens a pull request touching a pinned constraint
4. Before the first deployment to any new subscription
