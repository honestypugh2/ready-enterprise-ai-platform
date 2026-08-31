using './main.bicep'

param location = 'eastus'
param namePrefix = 'replen-demo'
param workspaceName = 'replen-law-wd63qvf6hchli'
param presenterPrincipalId = '638098ed-c52d-42b6-a371-fc3e44f4435f'
param resourceTags = {
  workload: 'warehouse-replenishment'
  environment: 'dev'
  classification: 'internal'
  owner: 'ai-platform'
  costCenter: 'CC12345'
  dataResidencyEnforced: 'true'
}
