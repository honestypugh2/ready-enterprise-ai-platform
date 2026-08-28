// Ready Enterprise AI Platform — subscription-scoped deployment.
//
// Subscription scope because the resource group is part of what is deployed. A
// template that assumes a group already exists cannot describe the whole
// environment, and the group is where the tags that drive cost attribution and
// data-residency reporting live.
//
// Preview with `scripts/deploy.sh --what-if`. A deployment you cannot preview
// is a deployment you cannot approve.

targetScope = 'subscription'

import { classification, environmentName, tags } from './types.bicep'

@description('Deployment environment. Governs SKUs, retention and network posture.')
param environment environmentName

@description('Primary region. No default — an unstated region is a residency decision nobody made.')
param location string

@description('Short workload name. Becomes the prefix for every resource name.')
@minLength(3)
@maxLength(12)
param workloadName string = 'reap'

@description('Highest data classification this environment is approved to process.')
param dataClassification classification = 'internal'

@description('Team accountable for the workload. Not an individual.')
param owner string

@description('Cost centre for showback. Cost attribution is meaningless without it.')
param costCenter string

param publisherEmail string
param publisherName string

@description('Container image for the API and worker. Both run from one image; the command selects the entry point.')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Deploy the AI Gateway. Off by default outside prod because a Developer-tier APIM takes ~45 minutes to provision.')
param deployApiGateway bool = false

@description('Deploy the Azure ML workspace for the specialized detector.')
param deployMachineLearning bool = true

@description('Deploy the VNet and private endpoints. Always on in prod, where public access is disabled; opt in for dev or test to rehearse the private posture.')
param deployPrivateNetworking bool = false

@description('Address space for the platform VNet. Must not overlap anything it will be peered with.')
param vnetAddressPrefix string = '10.42.0.0/16'

@description('Entra OpenID configuration URL for gateway token validation.')
param entraOpenIdConfig string = ''

@description('Application ID URI of the app registration fronting the gateway API.')
param entraAudience string = ''

@description('Leaving dry run on is the safe default. Turn it off deliberately, per environment, and record who did.')
param connectorDryRun bool = true

var namePrefix = '${workloadName}-${environment}'

// Derived, not asked for. Prod disables public access on every resource, so
// private networking there is not a choice — without it the deployment succeeds
// and produces resources nothing can reach.
var privateNetworking = environment == 'prod' || deployPrivateNetworking

var resourceTags tags = {
  workload: workloadName
  environment: environment
  classification: dataClassification
  owner: owner
  costCenter: costCenter
  dataResidencyEnforced: 'true'
}

resource rg 'Microsoft.Resources/resourceGroups@2025-04-01' = {
  name: 'rg-${namePrefix}'
  location: location
  tags: resourceTags
}

module monitor 'modules/monitor.bicep' = {
  scope: rg
  params: {
    location: location
    namePrefix: namePrefix
    environment: environment
    resourceTags: resourceTags
  }
}

module network 'modules/network.bicep' = if (privateNetworking) {
  scope: rg
  params: {
    location: location
    namePrefix: namePrefix
    environment: environment
    resourceTags: resourceTags
    workspaceId: monitor.outputs.result.workspaceId
    vnetAddressPrefix: vnetAddressPrefix
  }
}

module identity 'modules/identity.bicep' = {
  scope: rg
  params: {
    location: location
    namePrefix: namePrefix
    resourceTags: resourceTags
  }
}

module keyvault 'modules/keyvault.bicep' = {
  scope: rg
  params: {
    location: location
    namePrefix: namePrefix
    environment: environment
    resourceTags: resourceTags
    workspaceId: monitor.outputs.result.workspaceId
  }
}

module storage 'modules/storage.bicep' = {
  scope: rg
  params: {
    location: location
    namePrefix: namePrefix
    environment: environment
    resourceTags: resourceTags
    workspaceId: monitor.outputs.result.workspaceId
  }
}

module search 'modules/search.bicep' = {
  scope: rg
  params: {
    location: location
    namePrefix: namePrefix
    environment: environment
    resourceTags: resourceTags
    workspaceId: monitor.outputs.result.workspaceId
  }
}

module foundry 'modules/foundry.bicep' = {
  scope: rg
  params: {
    location: location
    namePrefix: namePrefix
    environment: environment
    resourceTags: resourceTags
    workspaceId: monitor.outputs.result.workspaceId
  }
}

module servicebus 'modules/servicebus.bicep' = {
  scope: rg
  params: {
    location: location
    namePrefix: namePrefix
    environment: environment
    resourceTags: resourceTags
    workspaceId: monitor.outputs.result.workspaceId
  }
}

module aml 'modules/aml.bicep' = if (deployMachineLearning) {
  scope: rg
  params: {
    location: location
    namePrefix: namePrefix
    environment: environment
    resourceTags: resourceTags
    workspaceId: monitor.outputs.result.workspaceId
    storageId: storage.outputs.storageId
    keyVaultId: keyvault.outputs.vaultId
    appInsightsId: monitor.outputs.result.appInsightsId
  }
}

module apim 'modules/apim.bicep' = if (deployApiGateway) {
  scope: rg
  params: {
    location: location
    namePrefix: namePrefix
    environment: environment
    resourceTags: resourceTags
    workspaceId: monitor.outputs.result.workspaceId
    foundryEndpoint: foundry.outputs.foundryEndpoint
    appInsightsId: monitor.outputs.result.appInsightsId
    publisherEmail: publisherEmail
    publisherName: publisherName
    entraOpenIdConfig: entraOpenIdConfig
    entraAudience: entraAudience
    apimSubnetId: privateNetworking ? network!.outputs.apimSubnetId : ''
  }
}

module rbac 'modules/rbac.bicep' = {
  scope: rg
  params: {
    apiPrincipalId: identity.outputs.result.apiPrincipalId
    workerPrincipalId: identity.outputs.result.workerPrincipalId
    searchPrincipalId: search.outputs.searchPrincipalId
    projectPrincipalId: foundry.outputs.projectPrincipalId
    storageName: storage.outputs.storageName
    searchName: search.outputs.searchName
    foundryName: foundry.outputs.foundryName
    keyVaultName: last(split(keyvault.outputs.vaultId, '/'))
    serviceBusNamespaceName: servicebus.outputs.namespaceName
  }
}

module privateEndpoints 'modules/privateendpoints.bicep' = if (privateNetworking) {
  scope: rg
  params: {
    location: location
    namePrefix: namePrefix
    resourceTags: resourceTags
    subnetId: network!.outputs.privateEndpointSubnetId
    dnsZoneIds: network!.outputs.dnsZoneIds
    storageId: storage.outputs.storageId
    keyVaultId: keyvault.outputs.vaultId
    searchId: search.outputs.searchId
    foundryId: foundry.outputs.foundryId
    serviceBusId: servicebus.outputs.namespaceId
    amlId: deployMachineLearning ? aml!.outputs.amlId : ''
    containerRegistryId: deployMachineLearning ? aml!.outputs.containerRegistryId : ''
  }
}

output resourceGroupName string = rg.name
output apiIdentityClientId string = identity.outputs.result.apiClientId
output workerIdentityClientId string = identity.outputs.result.workerClientId
output searchEndpoint string = search.outputs.searchEndpoint
output foundryEndpoint string = foundry.outputs.foundryEndpoint
output serviceBusFqdn string = servicebus.outputs.namespaceFqdn
output storageBlobEndpoint string = storage.outputs.blobEndpoint
output appInsightsConnectionString string = monitor.outputs.result.appInsightsConnectionString
output gatewayUrl string = deployApiGateway ? apim!.outputs.gatewayUrl : ''
output amlWorkspaceName string = deployMachineLearning ? aml!.outputs.amlName : ''
output vnetId string = privateNetworking ? network!.outputs.vnetId : ''

@description('Container Apps are deployed by the pipeline after the image exists. Values here are the inputs that deployment needs.')
output containerAppInputs object = {
  workspaceCustomerId: monitor.outputs.result.workspaceCustomerId
  apiIdentityResourceId: identity.outputs.result.apiResourceId
  workerIdentityResourceId: identity.outputs.result.workerResourceId
  containerImage: containerImage
  connectorDryRun: connectorDryRun
  smallModelDeployment: foundry.outputs.smallModelDeployment
  frontierModelDeployment: foundry.outputs.frontierModelDeployment
  infrastructureSubnetId: privateNetworking ? network!.outputs.containerAppsSubnetId : ''
}
