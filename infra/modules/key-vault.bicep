param location string
param tags object
param vaultName string

resource vault 'Microsoft.KeyVault/vaults@2026-05-15' = {
  name: vaultName
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    networkAcls: { defaultAction: 'Allow', bypass: 'AzureServices' }
  }
}

output vaultUri string = vault.properties.vaultUri
