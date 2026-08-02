output "vnet_id" {
  description = "ID of the virtual network."
  value       = azurerm_virtual_network.main.id
}

output "postgres_subnet_id" {
  description = "ID of the subnet delegated to PostgreSQL Flexible Server."
  value       = azurerm_subnet.postgres.id
}

output "apps_subnet_id" {
  description = "ID of the subnet delegated to Container Apps environments."
  value       = azurerm_subnet.apps.id
}

output "postgres_private_dns_zone_id" {
  description = "ID of the private DNS zone used by the PostgreSQL Flexible Server."
  value       = azurerm_private_dns_zone.postgres.id
}

output "postgres_private_dns_zone_link_id" {
  description = "ID of the VNet link for the PostgreSQL private DNS zone. Depend on this before creating the server."
  value       = azurerm_private_dns_zone_virtual_network_link.postgres.id
}
