// Test. The environment the evaluation gate runs against, so it must be
// close enough to production that a passing gate means something.
using '../../main.bicep'

param environment = 'test'
param location = 'eastus2'
param workloadName = 'reap'
param dataClassification = 'internal'
param owner = 'CHANGE-ME-team-alias'
param costCenter = 'CHANGE-ME'
param publisherEmail = 'CHANGE-ME@example.com'
param publisherName = 'CHANGE-ME Platform Team'

param deployApiGateway = true
param deployMachineLearning = true

// Test exercises the real write path against non-production systems of record.
param connectorDryRun = false
