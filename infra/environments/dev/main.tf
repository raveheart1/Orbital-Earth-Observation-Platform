terraform {
  # Configured at init time via -backend-config (see .github/workflows and
  # infra/bootstrap/README.md). Kept empty so no state location is hardcoded.
  backend "azurerm" {}
}

provider "azurerm" {
  features {}

  # The CI deploy identity only has Contributor on the dev resource group, so
  # it cannot register resource providers subscription-wide. The bootstrap
  # script registers everything this stack needs.
  resource_provider_registrations = "none"
}

locals {
  prefix        = "${var.project}-${var.environment}" # oeop-dev
  prefix_alnum  = replace(local.prefix, "-", "")      # oeopdev
  unique_suffix = var.unique_suffix != "" ? var.unique_suffix : random_string.suffix.result

  storage_account_name = "${local.prefix_alnum}${local.unique_suffix}"    # oeopdev<suffix>
  acr_name             = "${local.prefix_alnum}${local.unique_suffix}acr" # oeopdev<suffix>acr
  key_vault_name       = "kv-${local.prefix}-${local.unique_suffix}"      # <= 24 chars
  # The region is part of the server name: the PostgreSQL resource provider
  # reserves a failed/deleted server's name against its original location for
  # days, so a region move with an unchanged name 409s (InvalidResourceLocation).
  postgres_server_name = "psql-${local.prefix}-${var.location}-${local.unique_suffix}"

  api_image    = coalesce(var.api_image, "${module.acr.login_server}/oeop-api:${var.image_tag}")
  web_image    = coalesce(var.web_image, "${module.acr.login_server}/oeop-web:${var.image_tag}")
  worker_image = coalesce(var.worker_image, "${module.acr.login_server}/oeop-worker:${var.image_tag}")

  tags = {
    project     = var.project
    environment = var.environment
    managed_by  = "terraform"
    repository  = var.repository_url
  }
}

# The resource group is created by scripts/bootstrap-azure-github.sh (the CI
# deploy identity is scoped to it and cannot create resource groups), so it
# is consumed as a data source rather than managed here.
data "azurerm_resource_group" "main" {
  name = "rg-${local.prefix}"
}

# Random suffix for globally unique names when var.unique_suffix is not set.
# Persisted in state, so names stay stable across applies.
resource "random_string" "suffix" {
  length  = 6
  lower   = true
  upper   = false
  numeric = true
  special = false

  keepers = {
    project     = var.project
    environment = var.environment
  }
}

# PostgreSQL admin password. Generated once and kept stable via keepers;
# stored only in Key Vault (inside the composed database URL) and in state.
# special=false keeps the password safe to embed in a URL without encoding.
resource "random_password" "postgres_admin" {
  length  = 32
  special = false

  keepers = {
    project     = var.project
    environment = var.environment
  }
}

module "network" {
  source = "../../modules/network"

  name_prefix         = local.prefix
  location            = var.location
  resource_group_name = data.azurerm_resource_group.main.name
  tags                = local.tags
}

module "observability" {
  source = "../../modules/observability"

  name_prefix         = local.prefix
  location            = var.location
  resource_group_name = data.azurerm_resource_group.main.name
  log_retention_days  = 30
  tags                = local.tags
}

module "postgres" {
  source = "../../modules/postgres"

  server_name            = local.postgres_server_name
  location               = var.location
  resource_group_name    = data.azurerm_resource_group.main.name
  delegated_subnet_id    = module.network.postgres_subnet_id
  private_dns_zone_id    = module.network.postgres_private_dns_zone_id
  administrator_password = random_password.postgres_admin.result
  tags                   = local.tags

  # The flexible server requires the private DNS zone VNet *link* to exist,
  # not just the zone; module-level depends_on covers it.
  depends_on = [module.network]
}

module "storage" {
  source = "../../modules/storage"

  storage_account_name = local.storage_account_name
  location             = var.location
  resource_group_name  = data.azurerm_resource_group.main.name
  retention_days       = var.artifacts_retention_days
  tags                 = local.tags
}

module "acr" {
  source = "../../modules/acr"

  registry_name       = local.acr_name
  location            = var.location
  resource_group_name = data.azurerm_resource_group.main.name
  tags                = local.tags
}

module "keyvault" {
  source = "../../modules/keyvault"

  vault_name          = local.key_vault_name
  location            = var.location
  resource_group_name = data.azurerm_resource_group.main.name
  # asyncpg via SQLAlchemy — scheme must be postgresql+asyncpg.
  database_url = "postgresql+asyncpg://${module.postgres.administrator_login}:${random_password.postgres_admin.result}@${module.postgres.server_fqdn}:5432/${module.postgres.database_name}"
  tags         = local.tags
}

module "identity" {
  source = "../../modules/identity"

  name_prefix           = local.prefix
  location              = var.location
  resource_group_name   = data.azurerm_resource_group.main.name
  storage_account_id    = module.storage.storage_account_id
  key_vault_id          = module.keyvault.vault_id
  container_registry_id = module.acr.registry_id
  tags                  = local.tags
}

module "container_apps" {
  source = "../../modules/container_apps"

  name_prefix         = local.prefix
  location            = var.location
  resource_group_name = data.azurerm_resource_group.main.name
  environment         = var.environment
  deploy_workloads    = var.deploy_workloads
  web_custom_domains  = var.web_custom_domains

  log_analytics_workspace_id = module.observability.log_analytics_workspace_id
  infrastructure_subnet_id   = module.network.apps_subnet_id

  identity_id        = module.identity.app_identity_id
  identity_client_id = module.identity.app_identity_client_id
  acr_login_server   = module.acr.login_server

  api_image    = local.api_image
  web_image    = local.web_image
  worker_image = local.worker_image

  storage_account_name = module.storage.storage_account_name
  # trimsuffix: the app expects account URLs without a trailing slash.
  blob_account_url         = trimsuffix(module.storage.blob_endpoint, "/")
  queue_account_url        = trimsuffix(module.storage.queue_endpoint, "/")
  artifacts_container_name = module.storage.artifacts_container_name
  analysis_queue_name      = module.storage.analysis_queue_name
  poison_queue_name        = module.storage.poison_queue_name

  database_url_secret_id                 = module.keyvault.database_url_secret_id
  application_insights_connection_string = module.observability.application_insights_connection_string

  git_commit_sha = var.image_tag

  # Visitor-drawn areas are allowed but capped far tighter than the curated
  # predefined regions, so arbitrary public submissions stay cheap.
  allow_custom_areas      = tostring(var.allow_custom_areas)
  max_custom_aoi_area_km2 = tostring(var.max_custom_aoi_area_km2)

  tags = local.tags

  # Apps resolve Key Vault secrets and pull from ACR at create time, so the
  # identity's role assignments must exist first.
  depends_on = [module.identity]
}

# Optional cost guardrail — only created when BOTH budget_amount and
# budget_contact_email are provided (emails are never hardcoded).
resource "azurerm_consumption_budget_resource_group" "main" {
  count = var.budget_amount != null && var.budget_contact_email != null ? 1 : 0

  name              = "budget-${local.prefix}"
  resource_group_id = data.azurerm_resource_group.main.id

  amount     = var.budget_amount
  time_grain = "Monthly"

  time_period {
    # First day of the month of the first apply; ignored afterwards (see
    # ignore_changes) so the plan stays clean. timestamp() (not
    # plantimestamp()) because the latter evaluates to the year-1 zero value
    # during `terraform validate` and fails provider validation.
    start_date = formatdate("YYYY-MM-'01T00:00:00Z'", timestamp())
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = [var.budget_contact_email]
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = [var.budget_contact_email]
  }

  lifecycle {
    ignore_changes = [time_period]
  }
}
