// Types shared by every module.
//
// Kept in one file so an environment cannot describe itself two different ways
// in two different templates.

@export()
@description('Deployment environment. Governs SKUs, retention and network posture.')
type environmentName = 'dev' | 'test' | 'prod'

@export()
@description('Data classification the workload is approved to process.')
type classification = 'public' | 'internal' | 'confidential' | 'restricted'

@export()
type tags = {
  workload: string
  environment: environmentName
  classification: classification
  owner: string
  costCenter: string
  @description('Set false only for a workload with an approved exception on record.')
  dataResidencyEnforced: string
}

@export()
@description('The distinct identities the platform runs under. One per component, so an audit log can attribute an action to a component rather than to "the platform".')
type workloadIdentities = {
  apiPrincipalId: string
  workerPrincipalId: string
  apiClientId: string
  workerClientId: string
  apiResourceId: string
  workerResourceId: string
}

@export()
type monitorOutputs = {
  workspaceId: string
  workspaceCustomerId: string
  appInsightsConnectionString: string
  appInsightsId: string
}

@export()
@description('Well-known role definition ids. Assigning by id avoids a lookup that can silently resolve to the wrong role in a different cloud.')
var roleIds = {
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  storageBlobDataReader: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
  searchIndexDataReader: '1407120a-92aa-4202-b7e9-c0e197c71c8f'
  searchIndexDataContributor: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  searchServiceContributor: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  cognitiveServicesOpenAiUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  azureMlDataScientist: 'f6c7c914-8db3-469d-8ca1-694a8f32e121'
  serviceBusDataSender: '69a216fc-b8fb-44d8-bc22-1f3c2cd27a39'
  serviceBusDataReceiver: '4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0'
  monitoringMetricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
}
