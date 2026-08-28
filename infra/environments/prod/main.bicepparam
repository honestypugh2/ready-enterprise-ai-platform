// Production. Private endpoints, 365-day retention, zone redundancy,
// gateway required.
//
// This file is applied by the pipeline only. scripts/deploy.sh refuses to
// deploy prod from a workstation.
using '../../main.bicep'

param environment = 'prod'
param location = 'eastus2'
param workloadName = 'reap'
param dataClassification = 'confidential'
param owner = 'CHANGE-ME-team-alias'
param costCenter = 'CHANGE-ME'
param publisherEmail = 'CHANGE-ME@example.com'
param publisherName = 'CHANGE-ME Platform Team'

// Not optional in production. Token budgets and cost attribution belong at the
// gateway, where the caller cannot tamper with what is emitted.
param deployApiGateway = true
param deployMachineLearning = true

// Entra validation requires an app registration. Until these are set, the
// gateway attributes by header and subscription id only.
param entraOpenIdConfig = ''
param entraAudience = ''

// Real writes to real systems of record. The approval chain is what makes this
// safe, not the flag.
param connectorDryRun = false

// Not a choice in prod: public access is disabled on every resource, so
// without private endpoints the deployment succeeds and produces resources
// nothing can reach. main.bicep derives this rather than trusting the value.
param deployPrivateNetworking = true
param vnetAddressPrefix = '10.44.0.0/16'
