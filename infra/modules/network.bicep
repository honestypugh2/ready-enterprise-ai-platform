// Network foundation for private deployments.
//
// Exists because the prod parameters disable public access on every resource.
// Without private endpoints that produces resources nothing can reach — an
// environment that provisions cleanly and cannot serve a request.
//
// Subnet layout is deliberate rather than convenient:
//
//   * Container Apps needs a delegated subnet of its own, /23 minimum, and it
//     cannot share with anything.
//   * Private endpoints sit in a separate subnet so an NSG rule about them
//     does not accidentally govern the workload.
//   * APIM keeps its own subnet because its service endpoints and NSG
//     requirements are unlike anything else here.

import { environmentName, tags } from '../types.bicep'

param location string
param namePrefix string
param environment environmentName
param resourceTags tags
param workspaceId string

@description('Address space. Must not overlap anything it will be peered with.')
param vnetAddressPrefix string = '10.42.0.0/16'

param containerAppsSubnetPrefix string = '10.42.0.0/23'
param privateEndpointSubnetPrefix string = '10.42.2.0/24'
param apimSubnetPrefix string = '10.42.3.0/24'

resource privateEndpointNsg 'Microsoft.Network/networkSecurityGroups@2024-07-01' = {
  name: '${namePrefix}-nsg-pe'
  location: location
  tags: resourceTags
  properties: {
    securityRules: [
      {
        name: 'deny-inbound-internet'
        properties: {
          priority: 4000
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

resource apimNsg 'Microsoft.Network/networkSecurityGroups@2024-07-01' = {
  name: '${namePrefix}-nsg-apim'
  location: location
  tags: resourceTags
  properties: {
    securityRules: [
      {
        // Required by the APIM control plane. Omitting it puts the service
        // into a failed state that is slow and confusing to diagnose.
        name: 'allow-apim-management'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'ApiManagement'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRange: '3443'
        }
      }
      {
        name: 'allow-https-inbound'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRange: '443'
        }
      }
    ]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-07-01' = {
  name: '${namePrefix}-vnet'
  location: location
  tags: resourceTags
  properties: {
    addressSpace: { addressPrefixes: [vnetAddressPrefix] }
    subnets: [
      {
        name: 'container-apps'
        properties: {
          addressPrefix: containerAppsSubnetPrefix
          delegations: [
            {
              name: 'app-environments'
              properties: { serviceName: 'Microsoft.App/environments' }
            }
          ]
        }
      }
      {
        name: 'private-endpoints'
        properties: {
          addressPrefix: privateEndpointSubnetPrefix
          networkSecurityGroup: { id: privateEndpointNsg.id }
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: 'apim'
        properties: {
          addressPrefix: apimSubnetPrefix
          networkSecurityGroup: { id: apimNsg.id }
        }
      }
    ]
  }
}

// One zone per service. Each must be linked to the VNet or name resolution
// falls back to the public endpoint, which then fails on the firewall — the
// most common and least obvious private-endpoint misconfiguration.
var zoneNames = [
  'privatelink.blob.${az.environment().suffixes.storage}'
  'privatelink.vaultcore.azure.net'
  'privatelink.search.windows.net'
  'privatelink.cognitiveservices.azure.com'
  'privatelink.openai.azure.com'
  'privatelink.services.ai.azure.com'
  'privatelink.servicebus.windows.net'
  'privatelink.api.azureml.ms'
  'privatelink.notebooks.azure.net'
  'privatelink.azurecr.io'
]

resource dnsZones 'Microsoft.Network/privateDnsZones@2024-06-01' = [
  for zone in zoneNames: {
    name: zone
    location: 'global'
    tags: resourceTags
  }
]

resource dnsLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = [
  for (zone, index) in zoneNames: {
    parent: dnsZones[index]
    name: '${namePrefix}-link'
    location: 'global'
    properties: {
      virtualNetwork: { id: vnet.id }
      registrationEnabled: false
    }
  }
]

resource flowLogsWorkspace 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: privateEndpointNsg
  name: 'to-law'
  properties: {
    workspaceId: workspaceId
    logs: [{ categoryGroup: 'allLogs', enabled: true }]
  }
}

output vnetId string = vnet.id
output containerAppsSubnetId string = vnet.properties.subnets[0].id
output privateEndpointSubnetId string = vnet.properties.subnets[1].id
output apimSubnetId string = vnet.properties.subnets[2].id

@description('Zone ids by service, so a private endpoint module can look up the one it needs without repeating the zone names.')
output dnsZoneIds object = {
  blob: dnsZones[0].id
  keyVault: dnsZones[1].id
  search: dnsZones[2].id
  cognitiveServices: dnsZones[3].id
  openAi: dnsZones[4].id
  aiServices: dnsZones[5].id
  serviceBus: dnsZones[6].id
  machineLearningApi: dnsZones[7].id
  machineLearningNotebooks: dnsZones[8].id
  containerRegistry: dnsZones[9].id
}

output environmentName environmentName = environment
