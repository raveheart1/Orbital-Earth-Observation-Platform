# Basic SKU is plenty for dev; admin user disabled — pulls go through the
# user-assigned managed identity (AcrPull) and pushes through `az acr build`
# with the deployer's AAD identity.
resource "azurerm_container_registry" "main" {
  name                = var.registry_name
  location            = var.location
  resource_group_name = var.resource_group_name

  sku           = "Basic"
  admin_enabled = false

  tags = var.tags
}
