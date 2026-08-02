output "storage_account_id" {
  description = "ID of the storage account."
  value       = azurerm_storage_account.main.id
}

output "storage_account_name" {
  description = "Name of the storage account."
  value       = azurerm_storage_account.main.name
}

output "blob_endpoint" {
  description = "Primary blob service endpoint (https://<account>.blob.core.windows.net/)."
  value       = azurerm_storage_account.main.primary_blob_endpoint
}

output "queue_endpoint" {
  description = "Primary queue service endpoint (https://<account>.queue.core.windows.net/)."
  value       = azurerm_storage_account.main.primary_queue_endpoint
}

output "artifacts_container_name" {
  description = "Name of the artifacts container."
  value       = azurerm_storage_container.artifacts.name
}

output "analysis_queue_name" {
  description = "Name of the analysis jobs queue."
  value       = azurerm_storage_queue.analysis_jobs.name
}

output "poison_queue_name" {
  description = "Name of the poison queue."
  value       = azurerm_storage_queue.analysis_jobs_poison.name
}
