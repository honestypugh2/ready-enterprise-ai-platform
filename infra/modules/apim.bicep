// API Management as the AI Gateway.
//
// The gateway exists because it is the only hop that sees both the caller
// identity and the model's token usage, and the caller cannot tamper with what
// it emits. Token limits, cost attribution and egress hygiene therefore belong
// here, not in the application — the application's own rate limiter is a
// per-replica demonstration, and says so.
//
// Every resource is on the GA API version. The llm-* policies are policy XML,
// not ARM properties, so they need no preview surface;
// tests/contract/test_ai_gateway_policy.py fails if a preview version returns
// without an entry in docs/operations/preview-register.md.
//
// The named values below are references, not secrets. `entra-audience`
// requires an app registration, which needs privileges the deploying
// subscription may not grant. APIM resolves named values at apply time, so the
// JWT branch is composed into the policy only when both Entra values exist.

import { environmentName, tags } from '../types.bicep'

param location string
param namePrefix string
param environment environmentName
param resourceTags tags
param workspaceId string
param foundryEndpoint string
param appInsightsId string

@description('Connection string of the Entra-only Application Insights resource. The logger authenticates with the gateway identity, not the key it contains.')
param appInsightsConnectionString string

@description('Contact for gateway ownership. Appears on the developer portal, so it must be a team, not a person.')
param publisherEmail string
param publisherName string

@description('Per-caller token budget. A budget the application cannot raise for itself.')
param tokensPerMinutePerUser int = 20000

@description('Workload ids accepted from x-workload-id. Anything else is reported as `unregistered`, which keeps the metric dimension bounded.')
@minLength(1)
param allowedWorkloadIds string[] = ['manufacturing-quality']

@description('APIM subscription ids belonging to trusted server-side proxies. Only these may name the end user with x-user-id; every other caller is budgeted by its subscription.')
param trustedProxySubscriptionIds string[] = []

@description('OpenID configuration URL for Entra token validation.')
param entraOpenIdConfig string = ''

@description('Application ID URI of the app registration fronting this API.')
param entraAudience string = ''

@description('Moderate prompts and completions with Azure AI Content Safety. Off by default: the backend managed-identity credential it needs is a portal step no ARM API version exposes.')
param enableContentSafety bool = false

@description('Severity (0 most restrictive, 7 least) at or above which content is blocked, on the eight-level scale.')
@minValue(0)
@maxValue(7)
param contentSafetyThreshold int = 4

@description('APIM subnet. Empty deploys without VNet integration. Only Premium supports Internal mode, so a non-Premium tier stays External and says so.')
param apimSubnetId string = ''

var isPremium = environment == 'prod'
var vnetIntegrated = !empty(apimSubnetId)
var entraConfigured = !empty(entraOpenIdConfig) && !empty(entraAudience)
var cognitiveServicesBase = endsWith(foundryEndpoint, '/')
  ? take(foundryEndpoint, max(length(foundryEndpoint) - 1, 0))
  : foundryEndpoint

// Each marker is replaced with its fragment when the feature is configured and
// removed otherwise. The contract test composes the same four variants.
var policyXml = replace(
  replace(
    loadTextContent('../apim/ai-gateway.policy.xml'),
    '<!-- @fragment entra-jwt -->',
    entraConfigured ? loadTextContent('../apim/fragments/entra-jwt.xml') : ''
  ),
  '<!-- @fragment content-safety -->',
  enableContentSafety ? loadTextContent('../apim/fragments/content-safety.xml') : ''
)

// Logged so per-user and per-transaction cost can be attributed from request
// telemetry. Bodies are never logged: prompts and completions carry
// entitlement-scoped evidence.
var attributionHeaders = ['x-user-id', 'x-workload-id', 'x-correlation-id', 'x-tokens-consumed']
var noBody = { bytes: 0 }

resource apim 'Microsoft.ApiManagement/service@2024-05-01' = {
  name: '${namePrefix}-apim'
  location: location
  tags: resourceTags
  sku: {
    name: isPremium ? 'Premium' : 'Developer'
    capacity: 1
  }
  identity: { type: 'SystemAssigned' }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
    virtualNetworkType: vnetIntegrated ? (isPremium ? 'Internal' : 'External') : 'None'
    virtualNetworkConfiguration: vnetIntegrated ? { subnetResourceId: apimSubnetId } : null
    publicNetworkAccess: 'Enabled'
    // Key names are plural (`Protocols`). The singular form is accepted, stored
    // and ignored, which is how this posture once looked enforced but was not.
    customProperties: {
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Protocols.Tls10': 'False'
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Protocols.Tls11': 'False'
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Protocols.Ssl30': 'False'
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Backend.Protocols.Tls10': 'False'
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Backend.Protocols.Tls11': 'False'
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Backend.Protocols.Ssl30': 'False'
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Ciphers.TripleDes168': 'False'
    }
  }
}

resource tokenLimitValue 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = {
  parent: apim
  name: 'tokens-per-minute-per-user'
  properties: {
    displayName: 'tokens-per-minute-per-user'
    value: string(tokensPerMinutePerUser)
  }
}

resource workloadIdsValue 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = {
  parent: apim
  name: 'allowed-workload-ids'
  properties: {
    displayName: 'allowed-workload-ids'
    value: join(allowedWorkloadIds, ',')
  }
}

// A named value cannot be empty. `none` matches no subscription id.
resource trustedProxiesValue 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = {
  parent: apim
  name: 'trusted-proxy-subscription-ids'
  properties: {
    displayName: 'trusted-proxy-subscription-ids'
    value: empty(trustedProxySubscriptionIds) ? 'none' : join(trustedProxySubscriptionIds, ',')
  }
}

resource openIdConfigValue 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = if (entraConfigured) {
  parent: apim
  name: 'entra-openid-config'
  properties: {
    displayName: 'entra-openid-config'
    value: entraOpenIdConfig
  }
}

resource audienceValue 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = if (entraConfigured) {
  parent: apim
  name: 'entra-audience'
  properties: {
    displayName: 'entra-audience'
    value: entraAudience
  }
}

resource contentSafetyThresholdValue 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = if (enableContentSafety) {
  parent: apim
  name: 'content-safety-threshold'
  properties: {
    displayName: 'content-safety-threshold'
    value: string(contentSafetyThreshold)
  }
}

resource backend 'Microsoft.ApiManagement/service/backends@2024-05-01' = {
  parent: apim
  name: 'foundry'
  properties: {
    type: 'Single'
    protocol: 'http'
    url: '${foundryEndpoint}openai'
    tls: { validateCertificateChain: true, validateCertificateName: true }
    // One backend serves every deployment, because the deployment is only a
    // path segment, so a trip cuts off all of them. It therefore trips on
    // server faults only. Throttling is per deployment and per caller, and is
    // left to the deployment's own Retry-After and to llm-token-limit; counting
    // 429s here would let one caller take the whole gateway down by exhausting
    // one small deployment.
    circuitBreaker: {
      rules: [
        {
          name: 'backend-faults'
          failureCondition: {
            count: 3
            interval: 'PT1M'
            statusCodeRanges: [
              { min: 500, max: 599 }
            ]
          }
          tripDuration: 'PT1M'
          acceptRetryAfter: true
        }
      ]
    }
  }
}

// The AIServices account also serves Content Safety, so no second resource.
// Authorization credentials must be set to the system-assigned identity with
// resource https://cognitiveservices.azure.com in the portal; until then every
// moderated request fails closed.
resource contentSafetyBackend 'Microsoft.ApiManagement/service/backends@2024-05-01' = if (enableContentSafety) {
  parent: apim
  name: 'content-safety'
  properties: {
    type: 'Single'
    protocol: 'http'
    url: cognitiveServicesBase
    tls: { validateCertificateChain: true, validateCertificateName: true }
  }
}

resource api 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: 'foundry-inference'
  properties: {
    displayName: 'Foundry inference'
    description: 'Governed access to model deployments. Every call is attributed and budgeted.'
    path: 'openai'
    protocols: ['https']
    subscriptionRequired: true
    serviceUrl: '${foundryEndpoint}openai'
  }
}

// Chat Completions only: it is the one schema the reasoning adapter calls. A
// route is added when a caller exists for it and a test exercises it.
resource completions 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'chat-completions'
  properties: {
    displayName: 'Chat completions'
    method: 'POST'
    urlTemplate: '/deployments/{deployment-id}/chat/completions'
    templateParameters: [
      { name: 'deployment-id', type: 'string', required: true }
    ]
    request: {
      queryParameters: [
        { name: 'api-version', type: 'string', required: true, description: 'Azure OpenAI data-plane API version. The policy refuses a request without one.' }
      ]
    }
    responses: [{ statusCode: 200, description: 'Completion' }]
  }
}

@description('The policy is the control. It is kept as XML on disk so it is reviewable in a pull request rather than edited in a portal.')
resource apiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: api
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: policyXml
  }
  dependsOn: [
    tokenLimitValue
    workloadIdsValue
    trustedProxiesValue
    openIdConfigValue
    audienceValue
    contentSafetyThresholdValue
    backend
    contentSafetyBackend
    completions
  ]
}

// Application Insights has local auth disabled, so an instrumentation-key
// logger cannot write. The gateway identity holds Monitoring Metrics Publisher
// instead (infra/modules/rbac.bicep).
resource apimLogger 'Microsoft.ApiManagement/service/loggers@2024-05-01' = {
  parent: apim
  name: 'appinsights'
  properties: {
    loggerType: 'applicationInsights'
    resourceId: appInsightsId
    credentials: {
      connectionString: appInsightsConnectionString
      identityClientId: 'SystemAssigned'
    }
  }
}

// `metrics: true` is what lets llm-emit-token-metric publish at all. Sampling
// is 100% because cost attribution summed from a sample is an estimate.
resource apiDiagnostics 'Microsoft.ApiManagement/service/apis/diagnostics@2024-05-01' = {
  parent: api
  name: 'applicationinsights'
  properties: {
    loggerId: apimLogger.id
    metrics: true
    alwaysLog: 'allErrors'
    httpCorrelationProtocol: 'W3C'
    logClientIp: false
    verbosity: 'information'
    sampling: { samplingType: 'fixed', percentage: 100 }
    frontend: {
      request: { headers: [], body: noBody }
      response: { headers: attributionHeaders, body: noBody }
    }
    backend: {
      request: { headers: [], body: noBody }
      response: { headers: [], body: noBody }
    }
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: apim
  name: 'to-law'
  properties: {
    workspaceId: workspaceId
    logs: [{ categoryGroup: 'allLogs', enabled: true }]
    metrics: [{ category: 'AllMetrics', enabled: true }]
  }
}

output apimId string = apim.id
output apimName string = apim.name
output gatewayUrl string = apim.properties.gatewayUrl
output apimPrincipalId string = apim.identity.principalId
