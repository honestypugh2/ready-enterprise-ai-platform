// Service Bus — the platform event backbone.
//
// Duplicate detection is enabled on the topic rather than defended against in
// each subscriber. `packages/events/bus.py` provides the same guarantee
// locally, so the in-process and cloud modes behave identically.
//
// Sessions are off: platform events are correlated by id, not ordered by
// partition, and requiring session affinity would couple the consumers to the
// producer's partitioning.

import { environmentName, tags } from '../types.bicep'

param location string
param namePrefix string
param environment environmentName
param resourceTags tags
param workspaceId string

var isPremium = environment == 'prod'

resource namespace 'Microsoft.ServiceBus/namespaces@2024-01-01' = {
  name: '${namePrefix}-servicebus'
  location: location
  tags: resourceTags
  sku: {
    name: isPremium ? 'Premium' : 'Standard'
    tier: isPremium ? 'Premium' : 'Standard'
    capacity: isPremium ? 1 : null
  }
  identity: { type: 'SystemAssigned' }
  properties: {
    minimumTlsVersion: '1.2'
    disableLocalAuth: true
    publicNetworkAccess: isPremium ? 'Disabled' : 'Enabled'
    zoneRedundant: isPremium
  }
}

resource topic 'Microsoft.ServiceBus/namespaces/topics@2024-01-01' = {
  parent: namespace
  name: 'platform-events'
  properties: {
    requiresDuplicateDetection: true
    duplicateDetectionHistoryTimeWindow: 'PT10M'
    defaultMessageTimeToLive: 'P14D'
    maxSizeInMegabytes: isPremium ? 5120 : 1024
    supportOrdering: true
  }
}

resource workerSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2024-01-01' = {
  parent: topic
  name: 'worker'
  properties: {
    maxDeliveryCount: 5
    // Dead-letter rather than discard: an event nobody could process is a
    // finding, not a shrug.
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
    lockDuration: 'PT1M'
    defaultMessageTimeToLive: 'P14D'
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: namespace
  name: 'to-law'
  properties: {
    workspaceId: workspaceId
    logs: [{ categoryGroup: 'allLogs', enabled: true }]
    metrics: [{ category: 'AllMetrics', enabled: true }]
  }
}

output namespaceId string = namespace.id
output namespaceName string = namespace.name
output namespaceFqdn string = '${namespace.name}.servicebus.windows.net'
output topicName string = topic.name
output subscriptionName string = workerSubscription.name
