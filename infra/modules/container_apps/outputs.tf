output "environment_id" {
  description = "ID of the Container Apps managed environment."
  value       = azurerm_container_app_environment.main.id
}

output "environment_name" {
  description = "Name of the Container Apps managed environment."
  value       = azurerm_container_app_environment.main.name
}

output "default_domain" {
  description = "Default domain of the managed environment."
  value       = azurerm_container_app_environment.main.default_domain
}

# URLs are computed from the environment's default domain, so they are known
# even before the apps themselves are deployed (deploy_workloads=false).
output "api_url" {
  description = "Public URL of the API."
  value       = local.api_url
}

output "web_url" {
  description = "Public URL of the web frontend."
  value       = local.web_url
}

output "migration_job_name" {
  description = "Name of the manual migration job (null until workloads are deployed)."
  value       = var.deploy_workloads ? azurerm_container_app_job.migrate[0].name : null
}

output "seed_job_name" {
  description = "Name of the manual seed job (null until workloads are deployed)."
  value       = var.deploy_workloads ? azurerm_container_app_job.seed[0].name : null
}

output "worker_job_name" {
  description = "Name of the event-driven worker job (null until workloads are deployed)."
  value       = var.deploy_workloads ? azurerm_container_app_job.worker[0].name : null
}
