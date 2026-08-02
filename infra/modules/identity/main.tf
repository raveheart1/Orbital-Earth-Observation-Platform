# Runtime identity shared by the API, web, worker and jobs. The apps set
# AZURE_CLIENT_ID to this identity's client ID so DefaultAzureCredential
# picks it deterministically.
resource "azurerm_user_assigned_identity" "app" {
  name                = "id-${var.name_prefix}-app"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

# --- Storage data-plane access ------------------------------------------------

resource "azurerm_role_assignment" "app_storage_blob_contributor" {
  scope                = var.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_role_assignment" "app_storage_queue_contributor" {
  scope                = var.storage_account_id
  role_definition_name = "Storage Queue Data Contributor"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# Needed to create user-delegation SAS URLs for artifact downloads.
resource "azurerm_role_assignment" "app_storage_blob_delegator" {
  scope                = var.storage_account_id
  role_definition_name = "Storage Blob Delegator"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# --- Key Vault secret reads (Container Apps secret references) ----------------

resource "azurerm_role_assignment" "app_kv_secrets_user" {
  scope                = var.key_vault_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# --- Image pulls --------------------------------------------------------------

resource "azurerm_role_assignment" "app_acr_pull" {
  scope                = var.container_registry_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}
