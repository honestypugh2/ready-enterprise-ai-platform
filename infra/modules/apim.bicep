// API Management as the AI Gateway.
//
// The gateway exists because it is the only hop that sees both the caller
// identity and the model's token usage, and the caller cannot tamper with what
// it emits. Token limits, cost attribution and egress hygiene therefore belong
// here, not in the application — the application's own rate limiter is a
// per-replica demonstration, and says so.
//
// The named values below are references, not secrets. `entra-audience`
// requires an app registration, which needs privileges the deploying
// subscription may not grant; the policy resolves named values at apply time,
// so it can only be applied after they exist.

import { environmentName, tags } from '../types.bicep'

param location string
param namePrefix string
param environment environmentName
param resourceTags tags
param workspaceId string
param foundryEndpoint string
param appInsightsId string

@description('Contact for gateway ownership. Appears on the developer portal, so it must be a team, not a person.')
param publisherEmail string
param publisherName string

@description('Per-caller token budget. A budget the application cannot raise for itself.')
param tokensPerMinutePerUser int = 20000

@description('OpenID configuration URL for Entra token validation.')
param entraOpenIdConfig string = ''

@description('Application ID URI of the app registration fronting this API.')
param entraAudience string = ''

@description('APIM subnet. Empty deploys without VNet integration. Only Premium supports Internal mode, so a non-Premium tier stays External and says so.')
param apimSubnetId string = ''

var isPremium = environment == 'prod'
var vnetIntegrated = !empty(apimSubnetId)

resource apim 'Microsoft.ApiManagement/service@2024-06-01-preview' = {
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
    customProperties: {
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Protocol.Tls10': 'False'
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Protocol.Tls11': 'False'
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Backend.Protocol.Tls10': 'False'
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Backend.Protocol.Tls11': 'False'
    }
  }
}

resource tokenLimitValue 'Microsoft.ApiManagement/service/namedValues@2024-06-01-preview' = {
  parent: apim
  name: 'tokens-per-minute-per-user'
  properties: {
    displayName: 'tokens-per-minute-per-user'
    value: string(tokensPerMinutePerUser)
  }
}

resource openIdConfigValue 'Microsoft.ApiManagement/service/namedValues@2024-06-01-preview' = if (!empty(entraOpenIdConfig)) {
  parent: apim
  name: 'entra-openid-config'
  properties: {
    displayName: 'entra-openid-config'
    value: entraOpenIdConfig
  }
}

resource audienceValue 'Microsoft.ApiManagement/service/namedValues@2024-06-01-preview' = if (!empty(entraAudience)) {
  parent: apim
  name: 'entra-audience'
  properties: {
    displayName: 'entra-audience'
    value: entraAudience
  }
}

resource backend 'Microsoft.ApiManagement/service/backends@2024-06-01-preview' = {
  parent: apim
  name: 'foundry'
  properties: {
    protocol: 'http'
    url: '${foundryEndpoint}openai'
    tls: { validateCertificateChain: true, validateCertificateName: true }
  }
}

resource api 'Microsoft.ApiManagement/service/apis@2024-06-01-preview' = {
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

resource completions 'Microsoft.ApiManagement/service/apis/operations@2024-06-01-preview' = {
  parent: api
  name: 'chat-completions'
  properties: {
    displayName: 'Chat completions'
    method: 'POST'
    urlTemplate: '/deployments/{deployment-id}/chat/completions'
    templateParameters: [
      { name: 'deployment-id', type: 'string', required: true }
    ]
    responses: [{ statusCode: 200, description: 'Completion' }]
  }
}

@description('The policy is the control. It is kept as XML on disk so it is reviewable in a pull request rather than edited in a portal.')
resource apiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-06-01-preview' = {
  parent: api
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('../apim/ai-gateway.policy.xml')
  }
  dependsOn: [tokenLimitValue, openIdConfigValue, audienceValue, completions]
}

resource apimLogger 'Microsoft.ApiManagement/service/loggers@2024-06-01-preview' = {
  parent: apim
  name: 'appinsights'
  properties: {
    loggerType: 'applicationInsights'
    resourceId: appInsightsId
    credentials: {
      // Resolved from the linked resource with the gateway's identity.
      instrumentationKey: '{{appinsights-instrumentation-key}}'
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
