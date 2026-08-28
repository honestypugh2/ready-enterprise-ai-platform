// Log Analytics and Application Insights.
//
// Provisioned first, and everything else sends to it. A workload whose
// telemetry destination is created last is a workload whose first failures are
// invisible.

import { environmentName, monitorOutputs, tags } from '../types.bicep'

param location string
param namePrefix string
param environment environmentName
param resourceTags tags

@description('Retention must satisfy the workload\'s evidence-retention obligation, not the default.')
var retentionDays = environment == 'prod' ? 365 : 30

resource workspace 'Microsoft.OperationalInsights/workspaces@2025-02-01' = {
  name: '${namePrefix}-law'
  location: location
  tags: resourceTags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: retentionDays
    features: {
      // Traces carry retrieved passages and tool arguments by construction, so
      // the workspace is queryable only through Azure RBAC.
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: environment == 'prod' ? 'Disabled' : 'Enabled'
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${namePrefix}-appi'
  location: location
  tags: resourceTags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
    // Ingestion is via the connection string with a managed identity; a
    // published instrumentation key is a credential nobody rotates.
    DisableLocalAuth: true
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: environment == 'prod' ? 'Disabled' : 'Enabled'
  }
}

@description('Fires when the platform writes without a recorded approval. Should never fire; if it does, the control failed.')
resource unapprovedWriteAlert 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = {
  name: '${namePrefix}-alert-unapproved-write'
  location: location
  tags: resourceTags
  properties: {
    displayName: 'Write executed without an approval'
    severity: 0
    enabled: true
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    scopes: [workspace.id]
    criteria: {
      allOf: [
        {
          query: '''
AppTraces
| where Properties.event == "execute_write"
| where isempty(tostring(Properties.approval_id)) or tostring(Properties.approval_id) == "not-required"
| where tostring(Properties.approval_required) == "True"
| summarize Count = count() by bin(TimeGenerated, 5m)
'''
          timeAggregation: 'Total'
          metricMeasureColumn: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 }
        }
      ]
    }
    autoMitigate: false
  }
}

output result monitorOutputs = {
  workspaceId: workspace.id
  workspaceCustomerId: workspace.properties.customerId
  appInsightsConnectionString: appInsights.properties.ConnectionString
  appInsightsId: appInsights.id
}
