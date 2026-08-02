data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "main" {
  name                = var.vault_name
  location            = var.location
  resource_group_name = var.resource_group_name
  tenant_id           = data.azurerm_client_config.current.tenant_id

  sku_name                   = "standard"
  rbac_authorization_enabled = true
  # Purge protection intentionally OFF for dev so `terraform destroy` can
  # fully remove and re-create the vault without a purge-protection wait.
  purge_protection_enabled   = false
  soft_delete_retention_days = 7

  tags = var.tags
}

# The vault uses RBAC, and RG-scoped Contributor does NOT grant data-plane
# secret writes. Grant the deploying principal Key Vault Administrator on the
# vault so Terraform can manage secrets. The deploy identity holds
# "Role Based Access Control Administrator" on the resource group, so it can
# create this assignment for itself.
#
# NOTE: Azure RBAC propagation is eventually consistent; on a brand-new vault
# the very first apply can occasionally fail writing the secret with 403.
# Re-running the apply resolves it.
resource "azurerm_role_assignment" "deployer_kv_admin" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = var.database_url_secret_name
  value        = var.database_url
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"

  depends_on = [azurerm_role_assignment.deployer_kv_admin]
}
