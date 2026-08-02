variable "name_prefix" {
  description = "Naming prefix, e.g. oeop-dev."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group for the identities."
  type        = string
}

variable "storage_account_id" {
  description = "Storage account the app identity needs data access to."
  type        = string
}

variable "key_vault_id" {
  description = "Key Vault the app identity reads secrets from."
  type        = string
}

variable "container_registry_id" {
  description = "Container registry the app identity pulls images from."
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default     = {}
}
