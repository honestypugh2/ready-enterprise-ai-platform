// Role assignments — least privilege, stated as data.
//
// Two properties this file exists to make true and reviewable:
//
//   * The API can read evidence and call models. It cannot write to storage,
//     manage the search index, or administer anything.
//   * The reasoning path's identity has no write permission anywhere. A
//     compromised reasoning call inherits permissions that cannot mutate a
//     system of record.
//
// Assignments are by role definition id rather than by name: a name lookup can
// silently resolve to a different role in a different cloud.

import { roleIds } from '../types.bicep'

param apiPrincipalId string
param workerPrincipalId string
param searchPrincipalId string
param projectPrincipalId string
param storageName string
param searchName string
param foundryName string
param keyVaultName string
param serviceBusNamespaceName string

resource storage 'Microsoft.Storage/storageAccounts@2025-01-01' existing = {
  name: storageName
}

resource search 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: searchName
}

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryName
}

resource vault 'Microsoft.KeyVault/vaults@2024-11-01' existing = {
  name: keyVaultName
}

resource serviceBus 'Microsoft.ServiceBus/namespaces@2024-01-01' existing = {
  name: serviceBusNamespaceName
}

// The API reads the corpus and the evidence store. It never writes them.
resource apiBlobReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, apiPrincipalId, roleIds.storageBlobDataReader)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.storageBlobDataReader)
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// The worker seals audit receipts, so it is the only identity that may write
// blobs. The API proposes; the worker persists.
resource workerBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, workerPrincipalId, roleIds.storageBlobDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.storageBlobDataContributor)
    principalId: workerPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Query only. The platform never mutates the index at run time; indexing is a
// separate pipeline with a separate identity.
resource apiSearchReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: search
  name: guid(search.id, apiPrincipalId, roleIds.searchIndexDataReader)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.searchIndexDataReader)
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Search reads the corpus to build the index.
resource searchBlobReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, searchPrincipalId, roleIds.storageBlobDataReader)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.storageBlobDataReader)
    principalId: searchPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Required for integrated vectorization to enrich beyond the free-tier limit.
resource searchCognitiveUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundry
  name: guid(foundry.id, searchPrincipalId, roleIds.cognitiveServicesUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.cognitiveServicesUser)
    principalId: searchPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource apiOpenAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundry
  name: guid(foundry.id, apiPrincipalId, roleIds.cognitiveServicesOpenAiUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.cognitiveServicesOpenAiUser)
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// The Foundry project reads the index it grounds on.
resource projectSearchReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: search
  name: guid(search.id, projectPrincipalId, roleIds.searchIndexDataReader)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.searchIndexDataReader)
    principalId: projectPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// The API publishes facts; the worker consumes them. Neither can do both.
resource apiEventSender 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: serviceBus
  name: guid(serviceBus.id, apiPrincipalId, roleIds.serviceBusDataSender)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.serviceBusDataSender)
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource workerEventReceiver 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: serviceBus
  name: guid(serviceBus.id, workerPrincipalId, roleIds.serviceBusDataReceiver)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.serviceBusDataReceiver)
    principalId: workerPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource apiSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: vault
  name: guid(vault.id, apiPrincipalId, roleIds.keyVaultSecretsUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.keyVaultSecretsUser)
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
  }
}
