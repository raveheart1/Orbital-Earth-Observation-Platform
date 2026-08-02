# Bootstrap: Azure + GitHub wiring

Everything in `infra/environments/dev` assumes a small amount of one-time
setup that Terraform itself cannot create (its own state storage, the OIDC
identity it runs as, and the resource group its permissions are scoped to).
That setup is automated by [`scripts/bootstrap-azure-github.sh`](../../scripts/bootstrap-azure-github.sh).

## What the script creates

| Resource | Name | Purpose |
| --- | --- | --- |
| Resource group | `rg-oeop-bootstrap` | Holds state storage + deploy identity, outside Terraform's blast radius |
| Resource group | `rg-oeop-dev` | Everything Terraform manages lives here (deploy identity is Contributor on it only) |
| Storage account | `oeoptfstate<hash>` | Terraform remote state (`tfstate` container, key `dev.tfstate`); `<hash>` = first 6 hex chars of a SHA-256 of the subscription id, keeping the name unique per subscription |
| User-assigned identity | `id-oeop-deploy` | GitHub Actions federates into this via OIDC — no client secrets anywhere |
| Federated credential | `gh-dev-environment` | Subject `repo:<owner>/<repo>:environment:dev`, so only workflows using the `dev` environment can authenticate |
| Role assignments | — | `Contributor` + `Role Based Access Control Administrator` on `rg-oeop-dev`, `Storage Blob Data Contributor` on the state account, `Reader` on `rg-oeop-bootstrap` |
| GitHub environment | `dev` | Target of the federated credential |
| GitHub repo variables | `AZURE_*`, `TF_STATE_*` | Read by the workflows; deploy no-op-skips until they exist |

It also registers the Azure resource providers the stack needs
(`Microsoft.App`, `Microsoft.DBforPostgreSQL`, ...), because the Terraform
provider is configured with `resource_provider_registrations = "none"` — the
deploy identity has no subscription-level rights to register them itself.

## Prerequisites

- `az` logged in to the target subscription with **Owner** (or Contributor +
  User Access Administrator — role assignments need the latter)
- `gh` logged in with admin access to the repository
- A non-production subscription: the script **refuses to run** if the
  subscription name contains "prod" unless `OEOP_ALLOW_PROD=1` is set

## Usage

```bash
./scripts/bootstrap-azure-github.sh

# common overrides
AZURE_LOCATION=westeurope ./scripts/bootstrap-azure-github.sh
GITHUB_REPOSITORY=my-org/my-fork ./scripts/bootstrap-azure-github.sh
```

The script is idempotent — re-run it any time (e.g. after rotating the
identity or forking the repo).

## Remote state

The `backend "azurerm" {}` block in `infra/environments/dev/main.tf` is left
empty on purpose; workflows configure it at init time:

```bash
terraform init \
  -backend-config="resource_group_name=rg-oeop-bootstrap" \
  -backend-config="storage_account_name=oeoptfstate<hash>" \
  -backend-config="container_name=tfstate" \
  -backend-config="key=dev.tfstate" \
  -backend-config="use_oidc=true" \
  -backend-config="use_azuread_auth=true"
```

For local use, run the same `terraform init` with your own `az login` session
(drop the `use_oidc` line; `use_azuread_auth=true` works with CLI auth) —
you'll need `Storage Blob Data Contributor` on the state account.

## Deploy flow after bootstrap

1. Push to `main` (or dispatch `deploy-dev`).
2. Stage 1 apply creates foundation resources (`deploy_workloads=false`).
3. `az acr build` pushes `oeop-api`, `oeop-worker`, `oeop-web` images.
4. Stage 2 apply (`deploy_workloads=true`) creates the container apps + jobs.
5. Migration and seed jobs run, then endpoints are smoke-tested.
