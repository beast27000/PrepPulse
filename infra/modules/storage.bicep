param location string
param tags object
param storageName string

resource storage 'Microsoft.Storage/storageAccounts@2026-09-01' = {
  name: storageName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    accessTier: 'Hot'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2026-09-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 7 }
    containerDeleteRetentionPolicy: { enabled: true, days: 7 }
  }
}

resource backups 'Microsoft.Storage/storageAccounts/blobServices/containers@2026-09-01' = {
  parent: blobService
  name: 'backups'
  properties: { publicAccess: 'None' }
}

output resourceId string = storage.id
