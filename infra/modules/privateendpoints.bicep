// Private endpoints for every data-plane dependency.
//
// Kept in one module rather than scattered across the service modules, because
// the set of endpoints *is* the network posture: a reviewer should be able to
// read one file and know what the workload can reach and what can reach it.
//
// Each endpoint registers in its private DNS zone. An endpoint without a zone
// group resolves to the public name, which then fails on the firewall — the
// most common private-endpoint misconfiguration and the least obvious.

import { tags } from '../types.bicep'

param location string
param namePrefix string
param resourceTags tags
param subnetId string
param dnsZoneIds object

param storageId string
param keyVaultId string
param searchId string
param foundryId string
param serviceBusId string

@description('Empty when the workspace is not deployed. Bicep evaluates the condition, not the value, so the module still compiles.')
param amlId string = ''
param containerRegistryId string = ''

type endpointSpec = {
  name: string
  serviceId: string
  groupId: string
  zoneIds: string[]
}

var endpoints endpointSpec[] = [
  {
    name: 'blob'
    serviceId: storageId
    groupId: 'blob'
    zoneIds: [dnsZoneIds.blob]
  }
  {
    name: 'kv'
    serviceId: keyVaultId
    groupId: 'vault'
    zoneIds: [dnsZoneIds.keyVault]
  }
  {
    name: 'search'
    serviceId: searchId
    groupId: 'searchService'
    zoneIds: [dnsZoneIds.search]
  }
  {
    // One endpoint, three zones: an AI Services account is reachable by all
    // three names and a client may use any of them.
    name: 'foundry'
    serviceId: foundryId
    groupId: 'account'
    zoneIds: [dnsZoneIds.cognitiveServices, dnsZoneIds.openAi, dnsZoneIds.aiServices]
  }
  {
    name: 'sb'
    serviceId: serviceBusId
    groupId: 'namespace'
    zoneIds: [dnsZoneIds.serviceBus]
  }
]

resource privateEndpoints 'Microsoft.Network/privateEndpoints@2024-07-01' = [
  for endpoint in endpoints: {
    name: '${namePrefix}-pe-${endpoint.name}'
    location: location
    tags: resourceTags
    properties: {
      subnet: { id: subnetId }
      privateLinkServiceConnections: [
        {
          name: endpoint.name
          properties: {
            privateLinkServiceId: endpoint.serviceId
            groupIds: [endpoint.groupId]
          }
        }
      ]
    }
  }
]

resource dnsGroups 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-07-01' = [
  for (endpoint, index) in endpoints: {
    parent: privateEndpoints[index]
    name: 'default'
    properties: {
      privateDnsZoneConfigs: [
        for (zoneId, zoneIndex) in endpoint.zoneIds: {
          name: '${endpoint.name}-${zoneIndex}'
          properties: { privateDnsZoneId: zoneId }
        }
      ]
    }
  }
]

resource amlEndpoint 'Microsoft.Network/privateEndpoints@2024-07-01' = if (!empty(amlId)) {
  name: '${namePrefix}-pe-aml'
  location: location
  tags: resourceTags
  properties: {
    subnet: { id: subnetId }
    privateLinkServiceConnections: [
      {
        name: 'aml'
        properties: {
          privateLinkServiceId: amlId
          groupIds: ['amlworkspace']
        }
      }
    ]
  }
}

resource amlDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-07-01' = if (!empty(amlId)) {
  parent: amlEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'api', properties: { privateDnsZoneId: dnsZoneIds.machineLearningApi } }
      { name: 'notebooks', properties: { privateDnsZoneId: dnsZoneIds.machineLearningNotebooks } }
    ]
  }
}

resource acrEndpoint 'Microsoft.Network/privateEndpoints@2024-07-01' = if (!empty(containerRegistryId)) {
  name: '${namePrefix}-pe-acr'
  location: location
  tags: resourceTags
  properties: {
    subnet: { id: subnetId }
    privateLinkServiceConnections: [
      {
        name: 'acr'
        properties: {
          privateLinkServiceId: containerRegistryId
          groupIds: ['registry']
        }
      }
    ]
  }
}

resource acrDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-07-01' = if (!empty(containerRegistryId)) {
  parent: acrEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'registry', properties: { privateDnsZoneId: dnsZoneIds.containerRegistry } }
    ]
  }
}

output endpointNames array = [for endpoint in endpoints: endpoint.name]
