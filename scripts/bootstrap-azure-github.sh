#!/usr/bin/env bash
# =============================================================================
# bootstrap-azure-github.sh
#
# One-time (idempotent) bootstrap for the Orbital Earth Observation Platform
# dev environment. Run it as a human with Owner (or Contributor + User Access
# Administrator) on the target subscription, logged in with both `az` and `gh`.
#
# It creates:
#   - rg-oeop-bootstrap        resource group holding Terraform state + deploy identity
#   - rg-oeop-dev              resource group Terraform deploys into
#   - oeoptfstate<hash>        storage account for Terraform remote state
#   - id-oeop-deploy           user-assigned identity GitHub Actions federates into (OIDC)
#   - federated credential     subject repo:<owner>/<repo>:environment:dev
#   - role assignments         Contributor + RBAC Administrator on rg-oeop-dev,
#                              Storage Blob Data Contributor on the state account,
#                              Reader on rg-oeop-bootstrap
#   - GitHub environment `dev` and the repo variables the workflows read
#
# No secrets are created or printed anywhere — auth is OIDC only.
# Safe to re-run at any time.
# =============================================================================
set -euo pipefail

# --- helpers -----------------------------------------------------------------

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWARN:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

need() {
  command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not installed."
}

need az
need gh
need shasum

# --- 1. Subscription context + prod safety rail ------------------------------

log "Checking Azure subscription"
SUB_NAME=$(az account show --query name -o tsv) || die "Not logged in to Azure. Run 'az login' first."
SUB_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)
printf '    Subscription: %s\n    Id:           %s\n    Tenant:       %s\n' "$SUB_NAME" "$SUB_ID" "$TENANT_ID"

if printf '%s' "$SUB_NAME" | grep -qi 'prod'; then
  if [ "${OEOP_ALLOW_PROD:-}" != "1" ]; then
    die "Subscription name '$SUB_NAME' looks like production. This repo's safety rule refuses to bootstrap dev infrastructure into a prod subscription. If you really mean it, re-run with OEOP_ALLOW_PROD=1."
  fi
  warn "OEOP_ALLOW_PROD=1 set — continuing against a prod-looking subscription."
fi

# --- 2. GitHub context -------------------------------------------------------

log "Checking GitHub context"
GITHUB_LOGIN=$(gh api user -q .login) || die "Not logged in to GitHub. Run 'gh auth login' first."
REPO="${GITHUB_REPOSITORY:-$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "${GITHUB_LOGIN}/Orbital-Earth-Observation-Platform")}"
printf '    GitHub user:  %s\n    Repository:   %s\n' "$GITHUB_LOGIN" "$REPO"

# --- 3. Names (env-overridable) ----------------------------------------------

LOCATION="${AZURE_LOCATION:-eastus}"
BOOTSTRAP_RG="${BOOTSTRAP_RG:-rg-oeop-bootstrap}"
DEV_RG="${DEV_RG:-rg-oeop-dev}"
IDENTITY_NAME="${IDENTITY_NAME:-id-oeop-deploy}"
STATE_CONTAINER="${STATE_CONTAINER:-tfstate}"
# Short subscription hash keeps the storage account name globally unique,
# deterministic per subscription, lowercase alnum and well under 24 chars.
SUB_HASH=$(printf '%s' "$SUB_ID" | shasum -a 256 | cut -c1-6)
STATE_SA="${STATE_SA:-oeoptfstate${SUB_HASH}}"

log "Configuration"
printf '    Location:            %s\n' "$LOCATION"
printf '    Bootstrap RG:        %s\n' "$BOOTSTRAP_RG"
printf '    Dev RG:              %s\n' "$DEV_RG"
printf '    State account:       %s (container: %s)\n' "$STATE_SA" "$STATE_CONTAINER"
printf '    Deploy identity:     %s\n' "$IDENTITY_NAME"

# --- 4. Resource groups + state storage --------------------------------------

log "Creating resource groups (idempotent)"
az group create --name "$BOOTSTRAP_RG" --location "$LOCATION" --output none
az group create --name "$DEV_RG" --location "$LOCATION" --output none

log "Creating Terraform state storage account (idempotent)"
if ! az storage account show --name "$STATE_SA" --resource-group "$BOOTSTRAP_RG" --output none 2>/dev/null; then
  az storage account create \
    --name "$STATE_SA" \
    --resource-group "$BOOTSTRAP_RG" \
    --location "$LOCATION" \
    --sku Standard_LRS \
    --kind StorageV2 \
    --min-tls-version TLS1_2 \
    --allow-blob-public-access false \
    --output none \
    || die "Could not create storage account '$STATE_SA'. You need Contributor on '$BOOTSTRAP_RG', and the name must be globally unique."
fi

# container-rm uses the management plane, so it works with Contributor alone
# (plain 'az storage container create' would need a data-plane role).
az storage container-rm create \
  --storage-account "$STATE_SA" \
  --resource-group "$BOOTSTRAP_RG" \
  --name "$STATE_CONTAINER" \
  --output none

# --- 5. Deployment identity ---------------------------------------------------

log "Creating deployment identity (idempotent)"
az identity create \
  --name "$IDENTITY_NAME" \
  --resource-group "$BOOTSTRAP_RG" \
  --location "$LOCATION" \
  --output none
CLIENT_ID=$(az identity show --name "$IDENTITY_NAME" --resource-group "$BOOTSTRAP_RG" --query clientId -o tsv)
PRINCIPAL_ID=$(az identity show --name "$IDENTITY_NAME" --resource-group "$BOOTSTRAP_RG" --query principalId -o tsv)
printf '    clientId:    %s\n    principalId: %s\n' "$CLIENT_ID" "$PRINCIPAL_ID"

# --- 6. Federated credentials for GitHub OIDC --------------------------------

# GitHub presents one of two `sub` claim formats depending on repository
# settings/era: the classic `repo:<owner>/<repo>:environment:dev` or the
# ID-embedded immutable format `repo:<owner>@<ownerid>/<repo>@<repoid>:...`
# (the default for newer repositories). We register a credential for each so
# either token verifies. The authoritative prefix is exposed at
#   GET /repos/{owner}/{repo}/actions/oidc/customization/sub
SUB_PREFIX=$(gh api "repos/${REPO}/actions/oidc/customization/sub" -q .sub_claim_prefix 2>/dev/null || true)

# ensure_fc <credential name> <subject>
ensure_fc() {
  local name="$1" subject="$2"
  local existing
  existing=$(az identity federated-credential show \
    --name "$name" \
    --identity-name "$IDENTITY_NAME" \
    --resource-group "$BOOTSTRAP_RG" \
    --query subject -o tsv 2>/dev/null || true)
  if [ "$existing" = "$subject" ]; then
    printf '    OK (exists): %s -> %s\n' "$name" "$subject"
    return 0
  fi
  az identity federated-credential create \
    --name "$name" \
    --identity-name "$IDENTITY_NAME" \
    --resource-group "$BOOTSTRAP_RG" \
    --issuer "https://token.actions.githubusercontent.com" \
    --subject "$subject" \
    --audiences "api://AzureADTokenExchange" \
    --output none
  printf '    Created:     %s -> %s\n' "$name" "$subject"
}

log "Ensuring federated credentials"
ensure_fc gh-dev-environment "repo:${REPO}:environment:dev"
if [ -n "$SUB_PREFIX" ] && [ "$SUB_PREFIX" != "repo:${REPO}" ]; then
  ensure_fc gh-dev-environment-immutable "${SUB_PREFIX}:environment:dev"
fi

# --- 7. Role assignments ------------------------------------------------------

# ensure_role <role name> <scope>
ensure_role() {
  local role="$1" scope="$2"
  local existing
  existing=$(az role assignment list \
    --assignee "$PRINCIPAL_ID" \
    --role "$role" \
    --scope "$scope" \
    --query '[0].id' -o tsv 2>/dev/null || true)
  if [ -n "$existing" ]; then
    printf '    OK (exists): %s @ %s\n' "$role" "$scope"
    return 0
  fi
  if ! az role assignment create \
    --assignee-object-id "$PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal \
    --role "$role" \
    --scope "$scope" \
    --output none; then
    die "Failed to assign role '$role' at '$scope'. You need Owner or User Access Administrator on the subscription (or that scope) to create role assignments. Ask a subscription admin to run this script, or to grant you 'User Access Administrator'."
  fi
  printf '    Assigned:    %s @ %s\n' "$role" "$scope"
}

log "Assigning roles to the deployment identity"
DEV_RG_ID="/subscriptions/${SUB_ID}/resourceGroups/${DEV_RG}"
BOOTSTRAP_RG_ID="/subscriptions/${SUB_ID}/resourceGroups/${BOOTSTRAP_RG}"
STATE_SA_ID="/subscriptions/${SUB_ID}/resourceGroups/${BOOTSTRAP_RG}/providers/Microsoft.Storage/storageAccounts/${STATE_SA}"

# Contributor: create/update all dev resources.
ensure_role "Contributor" "$DEV_RG_ID"
# RBAC Administrator: Terraform creates role assignments (UAMI -> Storage/KV/ACR).
ensure_role "Role Based Access Control Administrator" "$DEV_RG_ID"
# Remote state access (data plane, used with use_azuread_auth=true).
ensure_role "Storage Blob Data Contributor" "$STATE_SA_ID"
# Read-only visibility of the bootstrap RG (state account metadata).
ensure_role "Reader" "$BOOTSTRAP_RG_ID"
# Key Vault purge happens at SUBSCRIPTION scope (deletedVaults/purge), so the
# RG-scoped Contributor cannot do it. This purge-only role lets Terraform
# destroy-and-purge vaults (e.g. replacements, destroy-dev) without 403s.
ensure_role "Key Vault Purge Operator" "/subscriptions/${SUB_ID}"

# --- 8. Resource providers ----------------------------------------------------

# The Terraform provider is configured with resource_provider_registrations =
# "none" (the deploy identity has no subscription-level rights), so register
# everything the stack needs here. Registration is async; first apply happens
# much later, so we don't wait.
log "Registering resource providers (async, idempotent)"
for ns in Microsoft.App Microsoft.ContainerRegistry Microsoft.DBforPostgreSQL \
  Microsoft.KeyVault Microsoft.ManagedIdentity Microsoft.Network \
  Microsoft.OperationalInsights Microsoft.Insights Microsoft.Storage \
  Microsoft.Consumption Microsoft.CostManagement; do
  az provider register --namespace "$ns" --output none \
    || warn "Could not register provider '$ns' (needs subscription Contributor). If a later terraform apply fails with 'subscription is not registered', ask an admin to run: az provider register --namespace $ns"
done

# --- 9. GitHub environment + variables ---------------------------------------

log "Creating GitHub environment 'dev'"
gh api --method PUT "repos/${REPO}/environments/dev" --silent \
  || die "Could not create the 'dev' environment on ${REPO}. You need admin access to the repository."

log "Setting GitHub repo variables"
set_var() {
  gh variable set "$1" --body "$2" --repo "$REPO" \
    || die "Failed to set repo variable '$1'. You need admin access to ${REPO}."
  printf '    %s=%s\n' "$1" "$2"
}
set_var AZURE_CLIENT_ID "$CLIENT_ID"
set_var AZURE_TENANT_ID "$TENANT_ID"
set_var AZURE_SUBSCRIPTION_ID "$SUB_ID"
set_var AZURE_LOCATION "$LOCATION"
set_var AZURE_RESOURCE_GROUP "$DEV_RG"
set_var TF_STATE_RESOURCE_GROUP "$BOOTSTRAP_RG"
set_var TF_STATE_STORAGE_ACCOUNT "$STATE_SA"
set_var TF_STATE_CONTAINER "$STATE_CONTAINER"

# --- 10. Summary --------------------------------------------------------------

log "Bootstrap complete"
cat <<EOF

  Subscription:      $SUB_NAME ($SUB_ID)
  State:             $STATE_SA/$STATE_CONTAINER (rg: $BOOTSTRAP_RG)
  Deploy identity:   $IDENTITY_NAME (clientId: $CLIENT_ID)
  Federated subject: $FC_SUBJECT
  Dev resource group: $DEV_RG

Next steps:
  1. Push to main (or run the 'deploy-dev' workflow manually) — it deploys
     foundation infra, builds images into ACR, then deploys the apps.
  2. The deploy workflow no-op-skips until these variables exist, so pushes
     made before running this script were skipped by design.
EOF
