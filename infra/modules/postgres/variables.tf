variable "server_name" {
  description = "Globally unique name for the PostgreSQL Flexible Server."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group for the server."
  type        = string
}

variable "delegated_subnet_id" {
  description = "ID of the subnet delegated to Microsoft.DBforPostgreSQL/flexibleServers."
  type        = string
}

variable "private_dns_zone_id" {
  description = "ID of the private DNS zone (*.postgres.database.azure.com) linked to the VNet."
  type        = string
}

variable "administrator_login" {
  description = "Admin login name."
  type        = string
  default     = "oeopadmin"
}

variable "administrator_password" {
  description = "Admin password (generated in the environment root, stored in Key Vault)."
  type        = string
  sensitive   = true
}

variable "sku_name" {
  description = "Server SKU. Burstable B1ms keeps dev cost low."
  type        = string
  default     = "B_Standard_B1ms"
}

variable "storage_mb" {
  description = "Storage in MB."
  type        = number
  default     = 32768
}

variable "backup_retention_days" {
  description = "Backup retention in days."
  type        = number
  default     = 7
}

variable "database_name" {
  description = "Application database name."
  type        = string
  default     = "oeop"
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default     = {}
}
