// Azure AI Search — the governed evidence index.
//
// Entitlement trimming happens in the retrieval plane before scoring, so the
// index itself never has to be the only line of defence. Local auth is
// disabled regardless: an API key for a search index is a key that ends up in
// a notebook.

import { environmentName, tags } from '../types.bicep'

param location string
param namePrefix string
param environment environmentName
param resourceTags tags
param workspaceId string

var sku = environment == 'prod' ? 'standard' : 'basic'

resource search 'Microsoft.Search/searchServices@2025-05-01' = {
  name: take('${namePrefix}-search', 60)
  location: location
  tags: resourceTags
  sku: { name: sku }
  identity: { type: 'SystemAssigned' }
  properties: {
    replicaCount: environment == 'prod' ? 3 : 1
    partitionCount: 1
    hostingMode: 'Default'
    // Entra only. `disableLocalAuth` is the setting that makes the RBAC story real.
    disableLocalAuth: true
    publicNetworkAccess: environment == 'prod' ? 'disabled' : 'enabled'
    semanticSearch: environment == 'prod' ? 'standard' : 'free'
    networkRuleSet: { ipRules: [] }
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: search
  name: 'to-law'
  properties: {
    workspaceId: workspaceId
    logs: [{ categoryGroup: 'allLogs', enabled: true }]
    metrics: [{ category: 'AllMetrics', enabled: true }]
  }
}

output searchId string = search.id
output searchName string = search.name
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output searchPrincipalId string = search.identity.principalId
