// Evidence storage.
//
// The audit container is provisioned with an immutability policy, because an
// audit record that can be quietly edited is not evidence. That is the whole
// reason this module exists — the rest is ordinary storage hardening.

import { environmentName, tags } from '../types.bicep'

param location string
param namePrefix string
param environment environmentName
param resourceTags tags
param workspaceId string

@description('Immutability window for sealed audit receipts. Set from the retention obligation, never from a default.')
@minValue(1)
@maxValue(3650)
param auditRetentionDays int = 365

var storageName = toLower(replace('${namePrefix}st', '-', ''))
var storageAccountName = take('${storageName}${uniqueString(resourceGroup().id)}', 24)

resource storage 'Microsoft.Storage/storageAccounts@2025-01-01' = {
  name: storageAccountName
  location: location
  tags: resourceTags
  sku: { name: environment == 'prod' ? 'Standard_ZRS' : 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    // Keys are the credential nobody rotates. Entra only.
    allowSharedKeyAccess: false
    allowBlobPublicAccess: false
    publicNetworkAccess: environment == 'prod' ? 'Disabled' : 'Enabled'
    defaultToOAuthAuthentication: true
    networkAcls: {
      defaultAction: environment == 'prod' ? 'Deny' : 'Allow'
      bypass: 'AzureServices'
    }
    encryption: {
      requireInfrastructureEncryption: true
      keySource: 'Microsoft.Storage'
      services: {
        blob: { enabled: true, keyType: 'Account' }
        file: { enabled: true, keyType: 'Account' }
      }
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-01-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 30 }
    containerDeleteRetentionPolicy: { enabled: true, days: 30 }
    isVersioningEnabled: true
  }
}

resource auditContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-01-01' = {
  parent: blobService
  name: 'audit'
  properties: {
    publicAccess: 'None'
    metadata: { purpose: 'sealed-audit-receipts' }
  }
}

@description('Write-once by storage policy rather than by convention. In prod the policy is locked, which makes it irreversible.')
resource auditImmutability 'Microsoft.Storage/storageAccounts/blobServices/containers/immutabilityPolicies@2025-01-01' = {
  parent: auditContainer
  name: 'default'
  properties: {
    immutabilityPeriodSinceCreationInDays: auditRetentionDays
    allowProtectedAppendWrites: false
  }
}

resource evidenceContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-01-01' = {
  parent: blobService
  name: 'evidence'
  properties: {
    publicAccess: 'None'
    metadata: { purpose: 'frames-passages-and-payloads-referenced-by-hash' }
  }
}

resource knowledgeContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-01-01' = {
  parent: blobService
  name: 'knowledge'
  properties: {
    publicAccess: 'None'
    metadata: { purpose: 'governed-source-corpus-for-retrieval' }
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: blobService
  name: 'to-law'
  properties: {
    workspaceId: workspaceId
    logs: [
      { category: 'StorageRead', enabled: true }
      { category: 'StorageWrite', enabled: true }
      { category: 'StorageDelete', enabled: true }
    ]
  }
}

output storageId string = storage.id
output storageName string = storage.name
output blobEndpoint string = storage.properties.primaryEndpoints.blob
