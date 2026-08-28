// User-assigned managed identities, one per component.
//
// A shared service principal makes an audit log say "the platform did it".
// Distinct identities are what make attribution possible, and what keep a
// compromised reasoning path unable to write.
//
// There is no secret here, and no code path in this repository accepts a
// connection string.

import { tags, workloadIdentities } from '../types.bicep'

param location string
param namePrefix string
param resourceTags tags

resource api 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: '${namePrefix}-id-api'
  location: location
  tags: resourceTags
}

resource worker 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: '${namePrefix}-id-worker'
  location: location
  tags: resourceTags
}

output result workloadIdentities = {
  apiPrincipalId: api.properties.principalId
  workerPrincipalId: worker.properties.principalId
  apiClientId: api.properties.clientId
  workerClientId: worker.properties.clientId
  apiResourceId: api.id
  workerResourceId: worker.id
}
