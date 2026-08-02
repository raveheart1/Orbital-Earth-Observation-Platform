output "vault_id" {
  description = "ID of the Key Vault."
  value       = azurerm_key_vault.main.id
}

output "vault_uri" {
  description = "URI of the Key Vault."
  value       = azurerm_key_vault.main.vault_uri
}

output "database_url_secret_id" {
  description = "Versionless ID of the database URL secret (Container Apps re-resolve it on new revisions)."
  value       = azurerm_key_vault_secret.database_url.versionless_id
}
