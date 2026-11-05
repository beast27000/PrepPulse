param vaultName string
param storageName string
param vmPrincipalId string
param deployerObjectId string

resource vault 'Microsoft.KeyVault/vaults@2026-05-15' existing = { name: vaultName }
resource storage 'Microsoft.Storage/storageAccounts@2026-09-01' existing = { name: storageName }

var officer = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7')
var user = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
var blobs = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')

resource deployerSecrets 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, deployerObjectId, officer)
  scope: vault
  properties: { roleDefinitionId: officer, principalId: deployerObjectId, principalType: 'User' }
}

resource vmSecrets 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, vmPrincipalId, user)
  scope: vault
  properties: { roleDefinitionId: user, principalId: vmPrincipalId, principalType: 'ServicePrincipal' }
}

resource vmBackups 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, vmPrincipalId, blobs)
  scope: storage
  properties: { roleDefinitionId: blobs, principalId: vmPrincipalId, principalType: 'ServicePrincipal' }
}
