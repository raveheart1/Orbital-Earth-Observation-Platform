variable "name_prefix" {
  description = "Naming prefix, e.g. oeop-dev."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group for the Container Apps resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment name passed to the apps (OEOP_ENVIRONMENT)."
  type        = string
}

variable "deploy_workloads" {
  description = "When false, only the managed environment is created (no apps/jobs). Solves the ACR chicken-and-egg on first deploy."
  type        = bool
  default     = false
}

variable "log_analytics_workspace_id" {
  description = "Log Analytics workspace for environment logs."
  type        = string
}

variable "infrastructure_subnet_id" {
  description = "Optional subnet (delegated to Microsoft.App/environments) for VNet integration. Required for private PostgreSQL access."
  type        = string
  default     = null
}

variable "identity_id" {
  description = "Resource ID of the user-assigned identity used by all apps and jobs."
  type        = string
}

variable "identity_client_id" {
  description = "Client ID of the user-assigned identity (AZURE_CLIENT_ID)."
  type        = string
}

variable "acr_login_server" {
  description = "Login server of the container registry images are pulled from."
  type        = string
}

variable "api_image" {
  description = "Full image reference for the API."
  type        = string
}

variable "web_image" {
  description = "Full image reference for the web frontend."
  type        = string
}

variable "worker_image" {
  description = "Full image reference for the worker."
  type        = string
}

variable "storage_account_name" {
  description = "Storage account name (used by the queue scale rule)."
  type        = string
}

variable "blob_account_url" {
  description = "Blob endpoint, e.g. https://<account>.blob.core.windows.net"
  type        = string
}

variable "queue_account_url" {
  description = "Queue endpoint, e.g. https://<account>.queue.core.windows.net"
  type        = string
}

variable "artifacts_container_name" {
  description = "Artifacts blob container name."
  type        = string
}

variable "analysis_queue_name" {
  description = "Analysis jobs queue name."
  type        = string
}

variable "poison_queue_name" {
  description = "Poison queue name."
  type        = string
}

variable "database_url_secret_id" {
  description = "Key Vault secret ID (versionless) for the database URL."
  type        = string
}

variable "application_insights_connection_string" {
  description = "Application Insights connection string."
  type        = string
  sensitive   = true
}

variable "git_commit_sha" {
  description = "Git commit SHA exposed to the apps (OEOP_GIT_COMMIT_SHA)."
  type        = string
}

variable "demo_mode" {
  description = "Value for OEOP_DEMO_MODE."
  type        = string
  default     = "true"
}

variable "min_replicas" {
  description = "Minimum replicas for the API and web apps (0 = scale to zero)."
  type        = number
  default     = 0
}

variable "max_replicas" {
  description = "Maximum replicas for the API and web apps."
  type        = number
  default     = 2
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default     = {}
}

variable "allow_custom_areas" {
  description = "Accept visitor-drawn areas of interest in addition to predefined regions"
  type        = string
  default     = "true"
}

variable "max_custom_aoi_area_km2" {
  description = <<-EOT
    Maximum area in km2 for a visitor-DRAWN area of interest. Deliberately far
    tighter than the predefined-region limit so arbitrary public submissions
    stay cheap to process.
  EOT
  type        = string
  default     = "2"
}
