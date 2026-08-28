// Development. Public endpoints, short retention, no gateway.
// Everything here is chosen for iteration speed, and none of it is a
// production posture.
using '../../main.bicep'

param environment = 'dev'
param location = 'eastus2'
param workloadName = 'reap'
param dataClassification = 'internal'
param owner = 'CHANGE-ME-team-alias'
param costCenter = 'CHANGE-ME'
param publisherEmail = 'CHANGE-ME@example.com'
param publisherName = 'CHANGE-ME Platform Team'

// Developer-tier APIM takes ~45 minutes to provision. Enable it deliberately.
param deployApiGateway = false
param deployMachineLearning = true

// Writes stay simulated in dev. Turning this off is a decision with a name
// attached, recorded in the deployment that made it.
param connectorDryRun = true
