resource "azurerm_postgresql_flexible_server" "main" {
  name                = var.server_name
  location            = var.location
  resource_group_name = var.resource_group_name

  version    = "16"
  sku_name   = var.sku_name
  storage_mb = var.storage_mb

  administrator_login    = var.administrator_login
  administrator_password = var.administrator_password

  # Private access (VNet integration) — no public network access.
  delegated_subnet_id           = var.delegated_subnet_id
  private_dns_zone_id           = var.private_dns_zone_id
  public_network_access_enabled = false

  backup_retention_days        = var.backup_retention_days
  geo_redundant_backup_enabled = false
  # Zone-redundant HA is intentionally OFF for dev (no high_availability block).
  # `zone` is left to Azure to choose; ignore drift so a service-side move
  # doesn't force replacement.

  tags = var.tags

  lifecycle {
    ignore_changes = [zone]
  }
}

# Allow-list the PostGIS extension so the app/migrations can CREATE EXTENSION.
resource "azurerm_postgresql_flexible_server_configuration" "azure_extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "POSTGIS"
}

resource "azurerm_postgresql_flexible_server_database" "oeop" {
  name      = var.database_name
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}
