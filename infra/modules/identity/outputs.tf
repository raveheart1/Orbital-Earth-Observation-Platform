output "app_identity_id" {
  description = "Resource ID of the app user-assigned identity."
  value       = azurerm_user_assigned_identity.app.id
}

output "app_identity_client_id" {
  description = "Client ID of the app user-assigned identity (for AZURE_CLIENT_ID)."
  value       = azurerm_user_assigned_identity.app.client_id
}

output "app_identity_principal_id" {
  description = "Principal (object) ID of the app user-assigned identity."
  value       = azurerm_user_assigned_identity.app.principal_id
}

output "role_assignment_ids" {
  description = "IDs of the app role assignments (depend on these before starting workloads that need data access)."
  value = [
    azurerm_role_assignment.app_storage_blob_contributor.id,
    azurerm_role_assignment.app_storage_queue_contributor.id,
    azurerm_role_assignment.app_storage_blob_delegator.id,
    azurerm_role_assignment.app_kv_secrets_user.id,
    azurerm_role_assignment.app_acr_pull.id,
  ]
}
