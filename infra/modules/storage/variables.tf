variable "storage_account_name" {
  description = "Globally unique storage account name (lowercase alphanumeric, 3-24 chars)."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group for the storage account."
  type        = string
}

variable "artifacts_container_name" {
  description = "Private blob container for analysis artifacts."
  type        = string
  default     = "artifacts"
}

variable "analysis_queue_name" {
  description = "Queue polled by the worker."
  type        = string
  default     = "analysis-jobs"
}

variable "poison_queue_name" {
  description = "Poison queue for failed analysis jobs."
  type        = string
  default     = "analysis-jobs-poison"
}

variable "retention_days" {
  description = "Days after which blobs under analyses/ are deleted by lifecycle management."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default     = {}
}
