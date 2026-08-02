variable "name_prefix" {
  description = "Naming prefix, e.g. oeop-dev."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group to create network resources in."
  type        = string
}

variable "vnet_address_space" {
  description = "Address space for the VNet."
  type        = list(string)
  default     = ["10.60.0.0/16"]
}

variable "postgres_subnet_prefix" {
  description = "Address prefix for the PostgreSQL delegated subnet."
  type        = string
  default     = "10.60.1.0/24"
}

variable "apps_subnet_prefix" {
  description = "Address prefix for the Container Apps delegated subnet (min /23 for Container Apps)."
  type        = string
  default     = "10.60.2.0/23"
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default     = {}
}
