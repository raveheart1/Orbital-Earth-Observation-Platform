output "server_id" {
  description = "ID of the PostgreSQL Flexible Server."
  value       = azurerm_postgresql_flexible_server.main.id
}

output "server_fqdn" {
  description = "FQDN of the PostgreSQL Flexible Server (resolves via the private DNS zone)."
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "database_name" {
  description = "Name of the application database."
  value       = azurerm_postgresql_flexible_server_database.oeop.name
}

output "administrator_login" {
  description = "Admin login name."
  value       = azurerm_postgresql_flexible_server.main.administrator_login
}
