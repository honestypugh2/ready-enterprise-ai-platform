// Key Vault.
//
// Holds no application credential. The platform authenticates with managed
// identities, so what lands here is the small set of things that genuinely
// cannot be an identity: a customer-supplied rate card key, an on-premises
// connector credential during migration.
//
// RBAC rather than access policies, and purge protection on, because a vault
// whose contents can be permanently deleted by one operator is not a control.

import { environmentName, tags } from '../types.bicep'

param location string
param namePrefix string
param environment environmentName
param resourceTags tags
param workspaceId string

resource vault 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: take('${namePrefix}-kv', 24)
  location: location
  tags: resourceTags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: tenant().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: environment == 'prod' ? 90 : 7
    enablePurgeProtection: environment == 'prod' ? true : null
    publicNetworkAccess: environment == 'prod' ? 'Disabled' : 'Enabled'
    networkAcls: {
      defaultAction: environment == 'prod' ? 'Deny' : 'Allow'
      bypass: 'AzureServices'
    }
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: vault
  name: 'to-law'
  properties: {
    workspaceId: workspaceId
    logs: [{ categoryGroup: 'audit', enabled: true }]
    metrics: [{ category: 'AllMetrics', enabled: true }]
  }
}

output vaultId string = vault.id
output vaultUri string = vault.properties.vaultUri
