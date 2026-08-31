// Development. Public endpoints, short retention, no gateway.
// Everything here is chosen for iteration speed, and none of it is a
// production posture.
using '../../main.bicep'

param environment = 'dev'
param location = 'eastus'
param workloadName = 'reap'
param dataClassification = 'internal'

// Synthetic fixture metadata for this repository and conference demo. These
// values do not identify a real team, cost centre, or monitored mailbox.
param owner = 'ai-platform'
param costCenter = 'CC12345'
param publisherEmail = 'ai-platform@microsoft.com'
param publisherName = 'AI Platform Team'

// APIM requires a real Entra app registration and an Entra-compatible logger
// configuration before its policy can be applied. The service is not part of
// the live replenishment path.
param deployApiGateway = false
param deployMachineLearning = true

// Writes stay simulated in dev. Turning this off is a decision with a name
// attached, recorded in the deployment that made it.
param connectorDryRun = true

// Public endpoints in dev. Set true to rehearse the private posture before
// prod, at the cost of needing a jump host to reach anything.
param deployPrivateNetworking = false
