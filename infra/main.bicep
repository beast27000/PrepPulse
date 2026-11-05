// Resource group already exists. The deployment deliberately uses its existing scope.
targetScope = 'resourceGroup'

param location string = 'centralindia'
param environmentName string = 'preppulse-pilot-b8bc'
param sessionId string = 'b8bcc939-16d7-4bb2-8a56-b41d36e00240'
param deployedBy string
param createdAt string
param deployerObjectId string
param adminUsername string = 'preppulse'

@description('A single operator IPv4 address with /32, or a controlled VPN CIDR. Never use *.')
@minLength(9)
param sshSourceCidr string

@description('OpenSSH public key only; never pass a private key.')
@minLength(50)
param sshPublicKey string

@allowed(['Standard_D2s_v5'])
param vmSize string = 'Standard_D2s_v5'

param vmName string = 'vm-preppulse-pilot-b8bc'
param networkName string = 'vnet-preppulse-pilot-b8bc'
param nsgName string = 'nsg-preppulse-pilot-b8bc'
param nicName string = 'nic-preppulse-pilot-b8bc'
param publicIpName string = 'pip-preppulse-pilot-b8bc'
param dnsLabel string = 'preppulse-pilot-b8bc'
param dataDiskName string = 'disk-preppulse-pilot-b8bc'
param storageName string = 'stpreppulsepilotb8bc'
param vaultName string = 'kv-preppulse-pilot-b8bc'

var tags = {
  'app-onboard-skill': 'true'
  'app-onboard-session-id': sessionId
  'created-at': createdAt
  environment: environmentName
  'deployed-by': deployedBy
  project: 'PrepPulse'
  purpose: 'five-day-pilot'
}

module compute './modules/compute.bicep' = {
  name: 'preppulse-compute'
  params: {
    location: location
    tags: tags
    vmName: vmName
    vmSize: vmSize
    networkName: networkName
    nsgName: nsgName
    nicName: nicName
    publicIpName: publicIpName
    dnsLabel: dnsLabel
    dataDiskName: dataDiskName
    sshPublicKey: sshPublicKey
    adminUsername: adminUsername
    sshSourceCidr: sshSourceCidr
  }
}

module storage './modules/storage.bicep' = {
  name: 'preppulse-storage'
  params: {
    location: location
    tags: tags
    storageName: storageName
  }
}

module vault './modules/key-vault.bicep' = {
  name: 'preppulse-key-vault'
  params: {
    location: location
    tags: tags
    vaultName: vaultName
  }
}

module roles './modules/role-assignments.bicep' = {
  name: 'preppulse-access'
  params: {
    vaultName: vaultName
    storageName: storageName
    vmPrincipalId: compute.outputs.principalId
    deployerObjectId: deployerObjectId
  }
  dependsOn: [vault, storage]
}

output hostname string = compute.outputs.hostname
output publicIp string = compute.outputs.ipAddress
output vmId string = compute.outputs.vmId
output vaultUri string = vault.outputs.vaultUri
output backupStorageAccount string = storageName
output backupContainer string = 'backups'
