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

output "custom_domain_verification_id" {
  description = "Value for the `asuid` TXT record proving ownership of a custom domain."
  value       = var.deploy_workloads ? azurerm_container_app.web[0].custom_domain_verification_id : null
  # The provider marks this sensitive. It is not a credential — it only proves
  # control of the DNS zone, and it has to be published as a TXT record — but
  # the output must declare it or the apply fails.
  sensitive = true
}

output "environment_static_ip" {
  description = "Static inbound IP of the environment; the A record target for an apex domain."
  value       = azurerm_container_app_environment.main.static_ip_address
}

output "web_custom_domain_urls" {
  description = "Public URLs served by the bound custom domains."
  value       = [for h in keys(local.web_custom_domains) : "https://${h}"]
}
