resource "azurerm_storage_account" "main" {
  name                = var.storage_account_name
  location            = var.location
  resource_group_name = var.resource_group_name

  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"

  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = false
  # Public network access stays enabled for dev (apps reach Storage over the
  # public endpoint with AAD auth), but the portal defaults to OAuth instead
  # of shared keys.
  public_network_access_enabled   = true
  default_to_oauth_authentication = true

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }

  tags = var.tags
}

resource "azurerm_storage_container" "artifacts" {
  name                  = var.artifacts_container_name
  storage_account_id    = azurerm_storage_account.main.id
  container_access_type = "private"
}

resource "azurerm_storage_queue" "analysis_jobs" {
  name               = var.analysis_queue_name
  storage_account_id = azurerm_storage_account.main.id
}

resource "azurerm_storage_queue" "analysis_jobs_poison" {
  name               = var.poison_queue_name
  storage_account_id = azurerm_storage_account.main.id
}

# Auto-expire analysis outputs: delete blobs under artifacts/analyses/ once
# they are older than var.retention_days.
resource "azurerm_storage_management_policy" "main" {
  storage_account_id = azurerm_storage_account.main.id

  rule {
    name    = "expire-analysis-artifacts"
    enabled = true

    filters {
      prefix_match = ["${azurerm_storage_container.artifacts.name}/analyses/"]
      blob_types   = ["blockBlob"]
    }

    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = var.retention_days
      }
    }
  }
}
