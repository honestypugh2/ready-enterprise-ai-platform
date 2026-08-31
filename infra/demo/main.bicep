targetScope = 'resourceGroup'

import { roleIds, tags } from '../types.bicep'

@description('Azure region shared by the existing replenishment demo resources.')
param location string = resourceGroup().location

@description('Prefix for the demo Search service.')
param namePrefix string = 'replen-demo'

@description('Existing Log Analytics workspace that receives Search diagnostics.')
param workspaceName string

@description('Presenter principal that creates the index and queries the synthetic corpus.')
param presenterPrincipalId string

@description('Tags identifying the synthetic conference demonstration.')
param resourceTags tags

var searchName = take('${namePrefix}-search', 60)

resource workspace 'Microsoft.OperationalInsights/workspaces@2025-02-01' existing = {
  name: workspaceName
}

module search '../modules/search.bicep' = {
  params: {
    location: location
    namePrefix: namePrefix
    environment: 'dev'
    resourceTags: resourceTags
    workspaceId: workspace.id
  }
}

resource searchService 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: searchName
}

resource presenterServiceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: searchService
  name: guid(searchService.id, presenterPrincipalId, roleIds.searchServiceContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      roleIds.searchServiceContributor
    )
    principalId: presenterPrincipalId
    principalType: 'User'
  }
  dependsOn: [search]
}

resource presenterDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: searchService
  name: guid(searchService.id, presenterPrincipalId, roleIds.searchIndexDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      roleIds.searchIndexDataContributor
    )
    principalId: presenterPrincipalId
    principalType: 'User'
  }
  dependsOn: [search]
}

output searchEndpoint string = search.outputs.searchEndpoint
output searchName string = search.outputs.searchName
