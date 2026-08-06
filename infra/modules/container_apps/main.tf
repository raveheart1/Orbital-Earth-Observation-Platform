locals {
  api_app_name  = "ca-${var.name_prefix}-api"
  web_app_name  = "ca-${var.name_prefix}-web"
  worker_job    = "caj-${var.name_prefix}-worker"
  migration_job = "caj-${var.name_prefix}-migrate"
  seed_job      = "caj-${var.name_prefix}-seed"

  # A subnet delegated to Microsoft.App/environments implies a workload
  # profiles environment, so declare the (serverless) Consumption profile and
  # pin every app/job to it. Without VNet integration no profile is used.
  workload_profile_name = var.infrastructure_subnet_id != null ? "Consumption" : null

  # Container app FQDNs are deterministic: <app>.<environment default domain>.
  # Computing them (instead of reading ingress attributes) breaks the
  # API <-> web URL cycle (API needs the web origin for CORS, web needs the
  # API base URL).
  api_url = "https://${local.api_app_name}.${azurerm_container_app_environment.main.default_domain}"
  web_url = "https://${local.web_app_name}.${azurerm_container_app_environment.main.default_domain}"

  database_url_secret_name = "database-url"
  appinsights_secret_name  = "appinsights-connection-string"

  # Environment shared by the API, worker and jobs. Entries carry either
  # `value` or `secret_name` (the other is null so every element has the
  # same object type).
  base_env = [
    { name = "OEOP_ENVIRONMENT", value = var.environment, secret_name = null },
    { name = "OEOP_DATABASE_URL", value = null, secret_name = local.database_url_secret_name },
    { name = "OEOP_BLOB_ACCOUNT_URL", value = var.blob_account_url, secret_name = null },
    { name = "OEOP_QUEUE_ACCOUNT_URL", value = var.queue_account_url, secret_name = null },
    { name = "OEOP_ARTIFACTS_CONTAINER", value = var.artifacts_container_name, secret_name = null },
    { name = "OEOP_ANALYSIS_QUEUE_NAME", value = var.analysis_queue_name, secret_name = null },
    { name = "OEOP_POISON_QUEUE_NAME", value = var.poison_queue_name, secret_name = null },
    { name = "OEOP_DEMO_MODE", value = var.demo_mode, secret_name = null },
    { name = "OEOP_ALLOW_CUSTOM_AREAS", value = var.allow_custom_areas, secret_name = null },
    { name = "OEOP_MAX_CUSTOM_AOI_AREA_KM2", value = var.max_custom_aoi_area_km2, secret_name = null },
    { name = "OEOP_GIT_COMMIT_SHA", value = var.git_commit_sha, secret_name = null },
    { name = "APPLICATIONINSIGHTS_CONNECTION_STRING", value = null, secret_name = local.appinsights_secret_name },
    { name = "AZURE_CLIENT_ID", value = var.identity_client_id, secret_name = null },
    { name = "OEOP_CORS_ALLOWED_ORIGINS", value = local.web_url, secret_name = null },
  ]

  api_env    = concat(local.base_env, [{ name = "OEOP_CONTAINER_IMAGE", value = var.api_image, secret_name = null }])
  worker_env = concat(local.base_env, [{ name = "OEOP_CONTAINER_IMAGE", value = var.worker_image, secret_name = null }])
}

resource "azurerm_container_app_environment" "main" {
  name                = "cae-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name

  logs_destination           = "log-analytics"
  log_analytics_workspace_id = var.log_analytics_workspace_id

  infrastructure_subnet_id = var.infrastructure_subnet_id

  dynamic "workload_profile" {
    for_each = local.workload_profile_name != null ? [1] : []
    content {
      name                  = "Consumption"
      workload_profile_type = "Consumption"
    }
  }

  tags = var.tags
}

# NOTE: no azurerm_monitor_diagnostic_setting on the managed environment.
# Application and system console logs already flow to Log Analytics via
# logs_destination above; the additional diagnostic categories exposed by
# Microsoft.App/managedEnvironments are inconsistent across API versions and
# regions, and azurerm support for them has been flaky, so it is deliberately
# skipped here.

# ------------------------------------------------------------------------------
# API (FastAPI, port 8000)
# ------------------------------------------------------------------------------

resource "azurerm_container_app" "api" {
  count = var.deploy_workloads ? 1 : 0

  name                         = local.api_app_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"
  workload_profile_name        = local.workload_profile_name

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  registry {
    server   = var.acr_login_server
    identity = var.identity_id
  }

  # Key Vault reference resolved with the user-assigned identity.
  secret {
    name                = local.database_url_secret_name
    identity            = var.identity_id
    key_vault_secret_id = var.database_url_secret_id
  }

  secret {
    name  = local.appinsights_secret_name
    value = var.application_insights_connection_string
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    container {
      name   = "api"
      image  = var.api_image
      cpu    = 0.5
      memory = "1Gi"

      dynamic "env" {
        for_each = local.api_env
        content {
          name        = env.value.name
          value       = env.value.value
          secret_name = env.value.secret_name
        }
      }

      liveness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health/live"
        initial_delay           = 10
        interval_seconds        = 15
        failure_count_threshold = 3
      }

      readiness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health/ready"
        interval_seconds        = 10
        failure_count_threshold = 3
      }
    }
  }

  tags = var.tags
}

# ------------------------------------------------------------------------------
# Web (Next.js standalone, port 3000)
# ------------------------------------------------------------------------------

resource "azurerm_container_app" "web" {
  count = var.deploy_workloads ? 1 : 0

  name                         = local.web_app_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"
  workload_profile_name        = local.workload_profile_name

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  registry {
    server   = var.acr_login_server
    identity = var.identity_id
  }

  ingress {
    external_enabled = true
    target_port      = 3000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    container {
      name   = "web"
      image  = var.web_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "API_BASE_URL"
        value = local.api_url
      }

      env {
        name  = "PORT"
        value = "3000"
      }

      liveness_probe {
        transport        = "HTTP"
        port             = 3000
        path             = "/"
        initial_delay    = 10
        interval_seconds = 15
      }

      readiness_probe {
        transport        = "HTTP"
        port             = 3000
        path             = "/"
        interval_seconds = 10
      }
    }
  }

  tags = var.tags
}

# ------------------------------------------------------------------------------
# Worker (event-driven job scaled on the analysis queue)
# ------------------------------------------------------------------------------

resource "azurerm_container_app_job" "worker" {
  count = var.deploy_workloads ? 1 : 0

  name                         = local.worker_job
  location                     = var.location
  resource_group_name          = var.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  workload_profile_name        = local.workload_profile_name

  replica_timeout_in_seconds = 1800
  replica_retry_limit        = 1

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  registry {
    server   = var.acr_login_server
    identity = var.identity_id
  }

  secret {
    name                = local.database_url_secret_name
    identity            = var.identity_id
    key_vault_secret_id = var.database_url_secret_id
  }

  secret {
    name  = local.appinsights_secret_name
    value = var.application_insights_connection_string
  }

  event_trigger_config {
    parallelism              = 1
    replica_completion_count = 1

    scale {
      min_executions              = 0
      max_executions              = 2
      polling_interval_in_seconds = 60

      # KEDA azure-queue scaler authenticated with the user-assigned managed
      # identity (`identity_id`, supported since azurerm 4.x) — no storage
      # keys or connection strings involved.
      rules {
        name             = "analysis-queue"
        custom_rule_type = "azure-queue"
        metadata = {
          queueName   = var.analysis_queue_name
          queueLength = "1"
          accountName = var.storage_account_name
          cloud       = "AzurePublicCloud"
        }
        identity_id = var.identity_id
      }
    }
  }

  template {
    container {
      name   = "worker"
      image  = var.worker_image
      cpu    = 0.5
      memory = "1Gi"

      dynamic "env" {
        for_each = local.worker_env
        content {
          name        = env.value.name
          value       = env.value.value
          secret_name = env.value.secret_name
        }
      }
    }
  }

  tags = var.tags
}

# ------------------------------------------------------------------------------
# Migration job (manual trigger): alembic upgrade head
# ------------------------------------------------------------------------------

resource "azurerm_container_app_job" "migrate" {
  count = var.deploy_workloads ? 1 : 0

  name                         = local.migration_job
  location                     = var.location
  resource_group_name          = var.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  workload_profile_name        = local.workload_profile_name

  replica_timeout_in_seconds = 900
  replica_retry_limit        = 1

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  registry {
    server   = var.acr_login_server
    identity = var.identity_id
  }

  secret {
    name                = local.database_url_secret_name
    identity            = var.identity_id
    key_vault_secret_id = var.database_url_secret_id
  }

  secret {
    name  = local.appinsights_secret_name
    value = var.application_insights_connection_string
  }

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      name   = "migrate"
      image  = var.api_image
      cpu    = 0.5
      memory = "1Gi"

      # Container Apps has no workingDir setting, and alembic must run from
      # /app/apps/api (where alembic.ini lives), so wrap the intended
      # ["python", "-m", "alembic", "upgrade", "head"] in a shell that cd's
      # first. The prod image has no uv, hence python -m.
      command = ["/bin/sh", "-c", "cd /app/apps/api && python -m alembic upgrade head"]

      dynamic "env" {
        for_each = local.api_env
        content {
          name        = env.value.name
          value       = env.value.value
          secret_name = env.value.secret_name
        }
      }
    }
  }

  tags = var.tags
}

# ------------------------------------------------------------------------------
# Seed job (manual trigger): seed reference regions, then ensure a demonstration
# analysis exists so the landing page always has a completed result to link to.
# `seed-demo --if-missing` is idempotent, so re-running on every deployment
# neither duplicates nor reprocesses.
# ------------------------------------------------------------------------------

resource "azurerm_container_app_job" "seed" {
  count = var.deploy_workloads ? 1 : 0

  name                         = local.seed_job
  location                     = var.location
  resource_group_name          = var.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  workload_profile_name        = local.workload_profile_name

  replica_timeout_in_seconds = 900
  replica_retry_limit        = 1

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  registry {
    server   = var.acr_login_server
    identity = var.identity_id
  }

  secret {
    name                = local.database_url_secret_name
    identity            = var.identity_id
    key_vault_secret_id = var.database_url_secret_id
  }

  secret {
    name  = local.appinsights_secret_name
    value = var.application_insights_connection_string
  }

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      name   = "seed"
      image  = var.api_image
      cpu    = 0.5
      memory = "1Gi"
      command = [
        "/bin/sh",
        "-c",
        "python -m oeop_api.cli seed-regions && python -m oeop_api.cli seed-demo --if-missing",
      ]

      dynamic "env" {
        for_each = local.api_env
        content {
          name        = env.value.name
          value       = env.value.value
          secret_name = env.value.secret_name
        }
      }
    }
  }

  tags = var.tags
}

# --- Custom domains -----------------------------------------------------
#
# Binding a hostname is a two-step handshake with DNS that Terraform cannot do
# on its own, so `web_custom_domains` stays empty until the records are live:
#
#   1. Ownership — a TXT record at `asuid.<host>` (or `asuid` for an apex)
#      holding the app's customDomainVerificationId.
#   2. Routing — a CNAME to the app's default hostname, or, for an apex domain
#      (which cannot CNAME), an A record to the environment's static IP.
#
# Azure issues the certificate only after both resolve, and it renews it
# automatically thereafter. Applying with a hostname whose DNS is not yet
# published fails the apply rather than waiting, which is why this is gated.
locals {
  web_custom_domains = var.deploy_workloads ? {
    for d in var.web_custom_domains : d.hostname => d
  } : {}
}

# Order matters, and it is the opposite of what it looks like. Azure refuses to
# issue a managed certificate for a hostname that is not already on an app in
# the environment:
#
#   RequireCustomHostnameInEnvironment: Creating managed certificate requires
#   hostname 'oeop.net' added as a custom hostname to a container app
#
# So the hostname is registered first with TLS disabled, and the certificate is
# issued against it afterwards. Azure then has to *attach* the certificate to
# the binding, which it will not let Terraform do in the same apply that
# creates them — the deploy workflow runs `az containerapp hostname bind` for
# that, which is why the certificate fields are ignored here. Without
# ignore_changes every subsequent apply would strip the certificate back off.
resource "azurerm_container_app_custom_domain" "web" {
  for_each = local.web_custom_domains

  name                     = each.key
  container_app_id         = azurerm_container_app.web[0].id
  certificate_binding_type = "Disabled"

  lifecycle {
    ignore_changes = [certificate_binding_type, container_app_environment_certificate_id]
  }
}

resource "azurerm_container_app_environment_managed_certificate" "web" {
  for_each = local.web_custom_domains

  # The hostname must exist on the app before this can be created.
  depends_on = [azurerm_container_app_custom_domain.web]

  name                         = "mc-${replace(each.key, ".", "-")}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  subject_name                 = each.key
  domain_control_validation    = each.value.validation

  tags = var.tags
}
