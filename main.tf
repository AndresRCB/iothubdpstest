resource "random_pet" "rg_name" {
  prefix = var.resource_group_name_prefix
}

resource "azurerm_resource_group" "main" {
  location = var.resource_group_location
  name     = random_pet.rg_name.id
}

# Create storage account & container
resource "random_string" "sa_name" {
  length  = 12
  special = false
  upper   = false
}

resource "azurerm_storage_account" "main" {
  name                     = random_string.sa_name.id
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "main" {
  name                  = "mycontainer"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

# Create an IoT Hub
resource "random_pet" "iothub_name" {
  prefix = var.iothub_name_prefix
  length = 1
}

resource "azurerm_iothub" "main" {
  name                = random_pet.iothub_name.id
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  sku {
    name     = "S1"
    capacity = 1
  }

  endpoint {
    type                       = "AzureIotHub.StorageContainer"
    connection_string          = azurerm_storage_account.main.primary_blob_connection_string
    name                       = "export"
    batch_frequency_in_seconds = 60
    max_chunk_size_in_bytes    = 10485760
    container_name             = azurerm_storage_container.main.name
    encoding                   = "Avro"
    file_name_format           = "{iothub}/{partition}_{YYYY}_{MM}_{DD}_{HH}_{mm}"
  }

  route {
    name           = "export"
    source         = "DeviceMessages"
    condition      = "true"
    endpoint_names = ["export"]
    enabled        = true
  }

  enrichment {
    key            = "tenant"
    value          = "$twin.tags.Tenant"
    endpoint_names = ["export"]
  }

  cloud_to_device {
    max_delivery_count = 30
    default_ttl        = "PT1H"
    feedback {
      time_to_live       = "PT1H10M"
      max_delivery_count = 15
      lock_duration      = "PT30S"
    }
  }

  tags = {
    purpose = "testing"
  }
}

#Create IoT Hub Access Policy
resource "azurerm_iothub_shared_access_policy" "main" {
  name                = "terraform-policy"
  resource_group_name = azurerm_resource_group.main.name
  iothub_name         = azurerm_iothub.main.name

  registry_read   = true
  registry_write  = true
  service_connect = true
}

# Create IoT Hub DPS
resource "random_pet" "dps_name" {
  prefix = var.dps_name_prefix
  length = 1
}

resource "azurerm_iothub_dps" "main" {
  name                = random_pet.dps_name.id
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  allocation_policy   = "Hashed"

  sku {
    name     = "S1"
    capacity = 1
  }

  linked_hub {
    connection_string       = azurerm_iothub_shared_access_policy.main.primary_connection_string
    location                = azurerm_resource_group.main.location
    allocation_weight       = 150
    apply_allocation_policy = true
  }
}

resource "azurerm_iothub_dps_certificate" "root" {
  name                = "root"
  resource_group_name = azurerm_resource_group.main.name
  iot_dps_name        = azurerm_iothub_dps.main.name
  is_verified         = true

  certificate_content = filebase64("./certificates/certs/azure-iot-test-only.root.ca.cert.pem")
}

resource "azurerm_iothub_dps_certificate" "intermediate" {
  name                = "intermediate"
  resource_group_name = azurerm_resource_group.main.name
  iot_dps_name        = azurerm_iothub_dps.main.name
  is_verified         = true

  certificate_content = filebase64("./certificates/certs/azure-iot-test-only.intermediate.cert.pem")
}
