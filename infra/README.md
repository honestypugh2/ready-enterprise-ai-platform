# Infrastructure

Bicep, subscription-scoped, WAF-aligned. Preview before you apply; nothing here
creates a resource without an explicit confirmation.

> **Nothing in this directory has been deployed.** Every template compiles and
> every parameter file validates, which is a different and much weaker claim.
> See [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md).

## Layout

```
infra/
├── main.bicep                  subscription scope; creates the resource group
├── types.bicep                 shared user-defined types and role definition ids
├── modules/
│   ├── monitor.bicep           Log Analytics, App Insights, the unapproved-write alert
│   ├── network.bicep           VNet, three subnets, NSGs, ten private DNS zones
│   ├── privateendpoints.bicep  one file that is the whole network posture
│   ├── identity.bicep          one user-assigned identity per component
│   ├── keyvault.bicep          RBAC-only, purge protection in prod
│   ├── storage.bicep           evidence + audit containers, immutability policy
│   ├── search.bicep            Azure AI Search, local auth disabled
│   ├── foundry.bicep           Foundry account, project, small + frontier deployments
│   ├── aml.bicep               Azure ML workspace and registry for the detector
│   ├── servicebus.bicep        event topic with duplicate detection and dead-lettering
│   ├── apim.bicep              AI Gateway
│   ├── containerapps.bicep     API and worker from one image
│   └── rbac.bicep              least-privilege role assignments
├── environments/{dev,test,prod}/main.bicepparam
├── apim/ai-gateway.policy.xml  token limits, cost attribution, egress hygiene
└── monitor/queries/*.kql       the six queries an operator actually opens
```

## Commands

```bash
make infra-lint                                  # compile and lint every template
scripts/deploy.sh --what-if --env dev            # preview (default posture)
scripts/deploy.sh --validate --env dev           # template validation
scripts/deploy.sh --apply --env dev              # deploy, after a confirmation prompt
```

`scripts/deploy.sh` **refuses to deploy `prod` from a workstation.** Production
runs from the pipeline, with workload identity federation and a recorded
approval.

## Decisions worth arguing with

**Subscription scope, not resource-group scope.** The resource group is part of
what is deployed. A template that assumes the group exists cannot describe the
whole environment, and the group is where the tags driving cost attribution and
residency reporting live.

**Local authentication is disabled everywhere it can be.** Search, Foundry,
Service Bus, Storage and App Insights ingestion all refuse keys. Every component
authenticates as its own managed identity. There is no code path in this
repository that accepts a connection string, and no secret in any parameter
file.

**One identity per component, not one per platform.** A shared service principal
makes an audit log say "the platform did it". Separate identities are what let a
receipt attribute an action to a component — and what keep a compromised
reasoning path holding permissions that cannot write.

**Two model deployments, not one.** The routing policy decides between a small
and a frontier model per task and records why. Provisioning only the frontier
model makes that decision unfalsifiable, and provisioning only the small one
makes the escalation path untestable.

**Model versions are pinned** (`versionUpgradeOption: NoAutoUpgrade`). A model
that upgrades itself invalidates every evaluation result recorded against it.

**The audit container has an immutability policy.** An audit record that can be
quietly deleted is not evidence. In prod the policy is locked, which makes it
irreversible — that is the point, and it is a decision to take deliberately.

**Semantic caching is off by default** in the gateway policy. A cache hit on a
governed explanation can return evidence retrieved for a different transaction
under a different entitlement. Enable it per route, only where responses carry
no entitlement-scoped content.

**Private networking is derived, not requested.** `deployPrivateNetworking` is
an opt-in for dev and test, but `main.bicep` computes
`environment == 'prod' || deployPrivateNetworking`. Prod disables public access
on every resource; a prod deployment without private endpoints succeeds and
produces an environment that cannot serve a request. That combination is not
reachable through a parameter file.

**Private endpoints live in one module.** The set of endpoints *is* the network
posture. Scattering them across the service modules means no single file
answers "what can this workload reach, and what can reach it".

**Every endpoint has a DNS zone group.** An endpoint without one resolves to the
public name and then fails on the firewall — the most common private-endpoint
misconfiguration and the least obvious to diagnose.

**The AML online endpoint is not provisioned here.** An endpoint without a
registered model deploys an empty shell that reports healthy and scores nothing,
which is worse than its absence. Deploy it from the model's own pipeline.

**Container Apps are deployed after the image exists.** `main.bicep` outputs the
inputs that deployment needs rather than pointing at a placeholder image and
pretending the platform is running.

## Preview features and prerequisites

The full register — including Python constraints, optional extras and the
non-version prerequisites — is
[docs/operations/preview-register.md](../docs/operations/preview-register.md).
The items below are the ones that will stop an infrastructure deployment.

| Item | Status |
|---|---|
| `Microsoft.CognitiveServices/accounts/projects` | GA surface, evolving. Verify against your subscription's available API versions before deploying. |
| Entra JWT validation at the gateway | **Requires an app registration** for `entra-audience`. APIM resolves named values at apply time, so the policy can only be applied after they exist. Until then the gateway attributes by header and subscription id. |
| APIM Developer tier | Provisions in roughly 45 minutes. `deployApiGateway` is off by default outside prod for that reason. |
| APIM `Internal` VNet mode | **Premium only.** With private networking on a non-Premium tier the gateway stays `External`; the template does this rather than failing, and this table is where that is stated. |
| Reaching a private environment | With `deployPrivateNetworking`, Container Apps ingress is internal and every data-plane endpoint is private. You will need a jump host, VPN or ExpressRoute to reach any of it — including to run `reap doctor`. |
| Container image pull over a private registry | The ACR private endpoint is provisioned, but Container Apps needs the registry reachable at pull time. Verify the managed identity has `AcrPull` **before** switching to a private image, or the revision fails to start with a misleading error. |

## Attribution

The APIM AI Gateway policy and the per-user cost attribution pattern are adapted
from [honestypugh2/wordpress-chatbot](https://github.com/honestypugh2/wordpress-chatbot)
(MIT). The subscription-scoped module layout and the WAF-aligned environment
split follow [honestypugh2/foundry-workload-studio](https://github.com/honestypugh2/foundry-workload-studio)
(MIT).
