// Container Apps hosting for the API and the worker.
//
// Two apps from one image: they share the same composition root, so shipping
// two images would mean two dependency sets that can drift apart. The command
// selects the entry point.
//
// Every setting below that names a dependency names an endpoint, never a
// credential. `REAP_MODE` is set explicitly rather than defaulted, because a
// deployment that inherits `local_mock` looks healthy and does nothing.

import { environmentName, tags } from '../types.bicep'

param location string
param namePrefix string
param environment environmentName
param resourceTags tags
param workspaceCustomerId string
@secure()
param workspaceSharedKey string
param appInsightsConnectionString string
param apiIdentityResourceId string
param workerIdentityResourceId string
param apiIdentityClientId string
param workerIdentityClientId string
param containerImage string
param searchEndpoint string
param foundryEndpoint string
param serviceBusFqdn string
param smallModelDeployment string
param frontierModelDeployment string

@description('Dry run stays on until a named operator turns it off for a named environment. The default must never be the permissive one.')
param connectorDryRun bool = true

@description('Delegated subnet for the managed environment. Empty deploys without VNet integration.')
param infrastructureSubnetId string = ''

var vnetIntegrated = !empty(infrastructureSubnetId)

// With VNet integration the API is reachable only from inside the network, so
// the gateway becomes the front door rather than an optional extra.
var externalIngress = !vnetIntegrated

var minReplicas = environment == 'prod' ? 2 : 1
var maxReplicas = environment == 'prod' ? 10 : 3

var sharedEnv = [
  { name: 'REAP_MODE', value: environment == 'prod' ? 'production' : 'azure_dev' }
  { name: 'REAP_ENVIRONMENT', value: environment }
  { name: 'REAP_DETECTOR_PROVIDER', value: 'aml' }
  { name: 'REAP_RETRIEVAL_PROVIDER', value: 'azure_search' }
  { name: 'REAP_RETRIEVAL_SEARCH_ENDPOINT', value: searchEndpoint }
  { name: 'REAP_REASONING_PROVIDER', value: 'foundry' }
  { name: 'REAP_REASONING_ENDPOINT', value: foundryEndpoint }
  { name: 'REAP_REASONING_SMALL_MODEL_DEPLOYMENT', value: smallModelDeployment }
  { name: 'REAP_REASONING_FRONTIER_MODEL_DEPLOYMENT', value: frontierModelDeployment }
  { name: 'REAP_CONNECTOR_DRY_RUN', value: string(connectorDryRun) }
  { name: 'REAP_OTEL_APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
  { name: 'REAP_SERVICEBUS_FQDN', value: serviceBusFqdn }
]

resource managedEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: '${namePrefix}-cae'
  location: location
  tags: resourceTags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspaceCustomerId
        sharedKey: workspaceSharedKey
      }
    }
    zoneRedundant: environment == 'prod'
    vnetConfiguration: vnetIntegrated
      ? {
          infrastructureSubnetId: infrastructureSubnetId
          internal: true
        }
      : null
  }
}

resource api 'Microsoft.App/containerApps@2025-01-01' = {
  name: '${namePrefix}-api'
  location: location
  tags: resourceTags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${apiIdentityResourceId}': {} }
  }
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: externalIngress
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'api'
          image: containerImage
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: concat(sharedEnv, [
            { name: 'AZURE_CLIENT_ID', value: apiIdentityClientId }
          ])
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/livez', port: 8000 }
              initialDelaySeconds: 10
              periodSeconds: 15
            }
            {
              // Readiness checks dependencies; liveness must not, or a
              // downstream outage restarts a healthy replica.
              type: 'Readiness'
              httpGet: { path: '/readyz', port: 8000 }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http'
            http: { metadata: { concurrentRequests: '40' } }
          }
        ]
      }
    }
  }
}

resource worker 'Microsoft.App/containerApps@2025-01-01' = {
  name: '${namePrefix}-worker'
  location: location
  tags: resourceTags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${workerIdentityResourceId}': {} }
  }
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: containerImage
          command: ['python', '-m', 'worker.main']
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: concat(sharedEnv, [
            { name: 'AZURE_CLIENT_ID', value: workerIdentityClientId }
          ])
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: environment == 'prod' ? 5 : 1
      }
    }
  }
}

output apiFqdn string = api.properties.configuration.ingress.fqdn
output apiIsInternal bool = vnetIntegrated
output apiId string = api.id
output workerId string = worker.id
output managedEnvironmentId string = managedEnvironment.id
