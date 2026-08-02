output "web_url" {
  description = "Public URL of the web frontend."
  value       = module.container_apps.web_url
}

output "api_url" {
  description = "Public URL of the API."
  value       = module.container_apps.api_url
}

output "resource_group_name" {
  description = "Resource group containing all dev resources."
  value       = data.azurerm_resource_group.main.name
}

output "acr_login_server" {
  description = "Login server of the container registry."
  value       = module.acr.login_server
}

output "storage_account_name" {
  description = "Name of the storage account."
  value       = module.storage.storage_account_name
}

output "container_apps_environment_name" {
  description = "Name of the Container Apps managed environment."
  value       = module.container_apps.environment_name
}

output "postgres_fqdn" {
  description = "FQDN of the PostgreSQL Flexible Server (private access only)."
  value       = module.postgres.server_fqdn
}

output "queue_name" {
  description = "Name of the analysis jobs queue."
  value       = module.storage.analysis_queue_name
}

output "app_identity_client_id" {
  description = "Client ID of the app user-assigned identity."
  value       = module.identity.app_identity_client_id
}

output "application_insights_connection_string" {
  description = "Application Insights connection string."
  value       = module.observability.application_insights_connection_string
  sensitive   = true
}

output "log_analytics_workspace_id" {
  description = "ID of the Log Analytics workspace."
  value       = module.observability.log_analytics_workspace_id
}

output "migration_job_name" {
  description = "Name of the manual migration Container Apps job (null until deploy_workloads=true)."
  value       = module.container_apps.migration_job_name
}

output "seed_job_name" {
  description = "Name of the manual seed Container Apps job (null until deploy_workloads=true)."
  value       = module.container_apps.seed_job_name
}
