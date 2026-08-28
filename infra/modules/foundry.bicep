// Microsoft Foundry account, project and model deployments.
//
// Two deployments are provisioned on purpose: a small model and a frontier
// model. The routing policy in `packages/model_router/policies/routing.yaml`
// decides between them per task, and records why. Provisioning only the
// frontier model would make that decision unfalsifiable.
//
// Local auth is disabled. The reasoning plane authenticates as its own
// identity and holds no key.

import { environmentName, tags } from '../types.bicep'

param location string
param namePrefix string
param environment environmentName
param resourceTags tags
param workspaceId string

@description('Small model for classification, extraction and short grounded explanation.')
param smallModel { name: string, version: string, capacity: int } = {
  name: 'gpt-4o-mini'
  version: '2024-07-18'
  capacity: 30
}

@description('Frontier model, reserved for tasks the routing policy proves need it.')
param frontierModel { name: string, version: string, capacity: int } = {
  name: 'gpt-4o'
  version: '2024-11-20'
  capacity: 10
}

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: '${namePrefix}-foundry'
  location: location
  tags: resourceTags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: '${namePrefix}-foundry'
    allowProjectManagement: true
    disableLocalAuth: true
    publicNetworkAccess: environment == 'prod' ? 'Disabled' : 'Enabled'
    networkAcls: {
      defaultAction: environment == 'prod' ? 'Deny' : 'Allow'
      bypass: 'AzureServices'
    }
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundry
  name: '${namePrefix}-project'
  location: location
  tags: resourceTags
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'Governed quality workload'
    description: 'Reference workload for the Beyond the Agent architecture patterns.'
  }
}

resource small 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundry
  name: smallModel.name
  sku: { name: 'GlobalStandard', capacity: smallModel.capacity }
  properties: {
    model: { format: 'OpenAI', name: smallModel.name, version: smallModel.version }
    versionUpgradeOption: 'NoAutoUpgrade'
    raiPolicyName: 'Microsoft.DefaultV2'
  }
}

// Serialised after the small deployment: concurrent deployments on one account
// race on capacity and fail intermittently.
resource frontier 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundry
  name: frontierModel.name
  sku: { name: 'GlobalStandard', capacity: frontierModel.capacity }
  properties: {
    model: { format: 'OpenAI', name: frontierModel.name, version: frontierModel.version }
    // Pinned. A model that upgrades itself invalidates every evaluation result
    // recorded against it.
    versionUpgradeOption: 'NoAutoUpgrade'
    raiPolicyName: 'Microsoft.DefaultV2'
  }
  dependsOn: [small]
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: foundry
  name: 'to-law'
  properties: {
    workspaceId: workspaceId
    logs: [
      { categoryGroup: 'audit', enabled: true }
      { categoryGroup: 'allLogs', enabled: true }
    ]
    metrics: [{ category: 'AllMetrics', enabled: true }]
  }
}

output foundryId string = foundry.id
output foundryName string = foundry.name
output foundryEndpoint string = foundry.properties.endpoint
output projectName string = project.name
output projectPrincipalId string = project.identity.principalId
output smallModelDeployment string = small.name
output frontierModelDeployment string = frontier.name
