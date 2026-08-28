// Azure Machine Learning workspace for the specialized models.
//
// This is where a real defect detector actually lives: a CNN trained on the
// customer's own inspection data, served from a managed online endpoint. The
// platform reaches it through `packages/detector/aml.py`, which speaks the
// endpoint's HTTPS scoring contract directly.
//
// The endpoint itself is not provisioned here. A managed online endpoint
// without a registered model deploys an empty shell that reports healthy and
// scores nothing, which is worse than its absence. Deploy it with the model,
// from the model's own pipeline.

import { environmentName, tags } from '../types.bicep'

param location string
param namePrefix string
param environment environmentName
param resourceTags tags
param workspaceId string
param storageId string
param keyVaultId string
param appInsightsId string

var registryPrefix = toLower(replace('${namePrefix}acr', '-', ''))
var registryName = take('${registryPrefix}${uniqueString(resourceGroup().id)}', 50)

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2025-04-01' = {
  name: registryName
  location: location
  tags: resourceTags
  sku: { name: environment == 'prod' ? 'Premium' : 'Basic' }
  properties: {
    // Admin user is a shared password. Pull is by managed identity.
    adminUserEnabled: false
    publicNetworkAccess: environment == 'prod' ? 'Disabled' : 'Enabled'
  }
}

resource aml 'Microsoft.MachineLearningServices/workspaces@2025-06-01' = {
  name: '${namePrefix}-aml'
  location: location
  tags: resourceTags
  sku: { name: 'Basic', tier: 'Basic' }
  identity: { type: 'SystemAssigned' }
  properties: {
    friendlyName: 'Specialized model workspace'
    description: 'Trains and serves the detector. Model quality is established here, not in the platform.'
    storageAccount: storageId
    keyVault: keyVaultId
    applicationInsights: appInsightsId
    containerRegistry: containerRegistry.id
    publicNetworkAccess: environment == 'prod' ? 'Disabled' : 'Enabled'
    hbiWorkspace: environment == 'prod'
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: aml
  name: 'to-law'
  properties: {
    workspaceId: workspaceId
    logs: [{ categoryGroup: 'allLogs', enabled: true }]
    metrics: [{ category: 'AllMetrics', enabled: true }]
  }
}

output amlId string = aml.id
output amlName string = aml.name
output amlPrincipalId string = aml.identity.principalId
output containerRegistryId string = containerRegistry.id
output containerRegistryLoginServer string = containerRegistry.properties.loginServer
