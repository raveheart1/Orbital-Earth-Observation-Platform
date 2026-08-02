variable "vault_name" {
  description = "Globally unique Key Vault name (3-24 chars, alphanumeric and hyphens)."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group for the vault."
  type        = string
}

variable "database_url" {
  description = "Composed application database URL (postgresql+asyncpg://...) stored as a secret."
  type        = string
  sensitive   = true
}

variable "database_url_secret_name" {
  description = "Name of the Key Vault secret holding the database URL."
  type        = string
  default     = "oeop-database-url"
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default     = {}
}
