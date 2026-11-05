param location string
param tags object
param vmName string
param vmSize string
param networkName string
param nsgName string
param nicName string
param publicIpName string
param dnsLabel string
param dataDiskName string
param sshPublicKey string
param adminUsername string
param sshSourceCidr string

resource nsg 'Microsoft.Network/networkSecurityGroups@2026-07-01' = {
  name: nsgName
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'HTTPS'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: 'Internet'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'HTTP-certificate-and-redirect'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '80'
          sourceAddressPrefix: 'Internet'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'SSH-operator-only'
        properties: {
          priority: 120
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '22'
          sourceAddressPrefix: sshSourceCidr
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2026-07-01' = {
  name: networkName
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.42.0.0/16'] }
    subnets: [
      {
        name: 'application'
        properties: {
          addressPrefix: '10.42.0.0/24'
          networkSecurityGroup: { id: nsg.id }
        }
      }
    ]
  }
}

resource publicIp 'Microsoft.Network/publicIPAddresses@2026-07-01' = {
  name: publicIpName
  location: location
  tags: tags
  sku: { name: 'Standard' }
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
    dnsSettings: { domainNameLabel: dnsLabel }
  }
}

resource nic 'Microsoft.Network/networkInterfaces@2026-07-01' = {
  name: nicName
  location: location
  tags: tags
  properties: {
    networkSecurityGroup: { id: nsg.id }
    ipConfigurations: [
      {
        name: 'primary'
        properties: {
          privateIPAllocationMethod: 'Dynamic'
          subnet: { id: resourceId('Microsoft.Network/virtualNetworks/subnets', networkName, 'application') }
          publicIPAddress: { id: publicIp.id }
        }
      }
    ]
  }
  dependsOn: [vnet]
}

resource dataDisk 'Microsoft.Compute/disks@2026-10-02' = {
  name: dataDiskName
  location: location
  tags: tags
  sku: { name: 'StandardSSD_LRS' }
  properties: {
    creationData: { createOption: 'Empty' }
    diskSizeGB: 64
    networkAccessPolicy: 'DenyAll'
    publicNetworkAccess: 'Disabled'
  }
}

resource vm 'Microsoft.Compute/virtualMachines@2026-04-01' = {
  name: vmName
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    hardwareProfile: { vmSize: vmSize }
    osProfile: {
      computerName: 'preppulse-pilot'
      adminUsername: adminUsername
      linuxConfiguration: {
        disablePasswordAuthentication: true
        provisionVMAgent: true
        patchSettings: { patchMode: 'ImageDefault' }
        ssh: {
          publicKeys: [
            { path: '/home/${adminUsername}/.ssh/authorized_keys', keyData: sshPublicKey }
          ]
        }
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: '0001-com-ubuntu-server-jammy'
        sku: '22_04-lts-gen2'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        diskSizeGB: 30
        managedDisk: { storageAccountType: 'StandardSSD_LRS' }
        deleteOption: 'Delete'
      }
      dataDisks: [
        {
          lun: 0
          createOption: 'Attach'
          managedDisk: { id: dataDisk.id }
          caching: 'None'
          deleteOption: 'Detach'
        }
      ]
    }
    networkProfile: {
      networkInterfaces: [{ id: nic.id, properties: { primary: true } }]
    }
    diagnosticsProfile: { bootDiagnostics: { enabled: true } }
  }
}

output hostname string = publicIp.properties.dnsSettings.fqdn
output ipAddress string = publicIp.properties.ipAddress
output vmId string = vm.id
output principalId string = vm.identity.principalId
