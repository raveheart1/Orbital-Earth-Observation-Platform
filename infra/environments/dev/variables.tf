variable "project" {
  description = "Project short name used in resource names."
  type        = string
  default     = "oeop"
}

variable "environment" {
  description = "Environment name."
  type        = string
  default     = "dev"
}

# Planetary Computer data lives in West Europe, but eastus keeps demo latency
# low for US users and PC assets are served over HTTPS from anywhere, so
# co-locating compute with the data is not required for this demo. Change the
# region here (or via AZURE_LOCATION in the bootstrap script) if your users
# are elsewhere — the tradeoff is only STAC/asset fetch latency, not
# correctness.
variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "eastus"
}

variable "unique_suffix" {
  description = "Optional lowercase alphanumeric suffix for globally unique names (storage, ACR, Key Vault, Postgres). Leave empty to use a random suffix persisted in state."
  type        = string
  default     = ""

  validation {
    condition     = can(regex("^[a-z0-9]{0,8}$", var.unique_suffix))
    error_message = "unique_suffix must be 0-8 lowercase alphanumeric characters."
  }
}

variable "image_tag" {
  description = "Tag for the application images (usually the git SHA)."
  type        = string
  default     = "latest"
}

variable "api_image" {
  description = "Full image reference for the API. Defaults to <acr>/oeop-api:<image_tag>."
  type        = string
  default     = null
}

variable "web_image" {
  description = "Full image reference for the web frontend. Defaults to <acr>/oeop-web:<image_tag>."
  type        = string
  default     = null
}

variable "worker_image" {
  description = "Full image reference for the worker. Defaults to <acr>/oeop-worker:<image_tag>."
  type        = string
  default     = null
}

# Two-stage deploy: stage 1 (false) creates only foundation resources —
# network, Postgres, storage, ACR, Key Vault, identity, observability and the
# Container Apps environment. Images are then pushed to the freshly created
# ACR, and stage 2 (true) creates the container apps and jobs that reference
# them. This solves the "apps need images from an ACR that doesn't exist yet"
# chicken-and-egg.
variable "deploy_workloads" {
  description = "Whether to create the container apps and jobs (stage 2)."
  type        = bool
  default     = false
}

variable "budget_contact_email" {
  description = "Email address to notify on budget thresholds. Budget is only created when both this and budget_amount are set. Never hardcode an email here — pass it via tfvars or -var."
  type        = string
  default     = null
}

variable "budget_amount" {
  description = "Monthly budget amount in the subscription currency. Budget is only created when both this and budget_contact_email are set."
  type        = number
  default     = null
}

variable "artifacts_retention_days" {
  description = "Days after which blobs under analyses/ are deleted."
  type        = number
  default     = 30
}

variable "repository_url" {
  description = "Repository URL used for the `repository` tag."
  type        = string
  default     = "https://github.com/ScoreSage/Orbital-Earth-Observation-Platform"
}

variable "allow_custom_areas" {
  description = "Accept visitor-drawn areas of interest in addition to predefined regions"
  type        = bool
  default     = true
}

variable "max_custom_aoi_area_km2" {
  description = "Maximum area in km2 for a visitor-drawn area of interest"
  type        = number
  default     = 2
}
