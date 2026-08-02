# Deployment

How the platform gets from a git commit to a running Azure environment. The
design goals: **no client secrets anywhere**, reproducible infrastructure
(Terraform with remote state), and images traceable to commits (tagged with
the git SHA).

Related: [architecture.md](architecture.md#local-vs-azure),
[security.md](security.md#identity-no-client-secrets-anywhere),
[operations.md](operations.md), [ADR 0005](adr/0005-managed-identity-oidc.md).

## Prerequisites

- **Azure CLI** (`az`) logged in to the target subscription:
  `az login`, then `az account set --subscription <id>`.
- **GitHub CLI** (`gh`) authenticated with access to
  `raveheart1/Orbital-Earth-Observation-Platform`: `gh auth login`.
- A **non-production subscription**. This is enforced, not just advised: the
  bootstrap script refuses subscriptions with "prod" in the name (see
  below).
- Sufficient permissions to create resource groups, role assignments, and
  Azure AD app registrations/federated credentials.

Local development requires none of this — the full stack runs against
Azurite and local PostGIS with `make dev` (see
[architecture.md](architecture.md#local-vs-azure)).

## Bootstrap: `scripts/bootstrap-azure-github.sh`

One-time setup that connects GitHub Actions to Azure without any stored
secret. What it creates:

1. **An Azure AD application with federated credentials** for GitHub OIDC,
   scoped to this repository and the GitHub environment `dev`. GitHub
   Actions exchanges its own OIDC token for short-lived Azure credentials at
   run time — there is no client secret to store, leak, or rotate.
2. **Role assignments** for that identity on the target scope (enough to run
   Terraform and push to ACR).
3. **A storage account and container for Terraform remote state**, so state
   is shared, locked, and survives laptops.
4. **GitHub environment configuration**: it sets the variables the deploy
   workflow reads:

   | Variable | Meaning |
   | --- | --- |
   | `AZURE_CLIENT_ID` | The federated app's client id (an identifier, not a secret) |
   | `AZURE_TENANT_ID` | Azure AD tenant |
   | `AZURE_SUBSCRIPTION_ID` | Target subscription |
   | `AZURE_LOCATION` | Deploy region (default `eastus`; see the [region trade-off](cost-and-scaling.md#region-trade-off-eastus-vs-westeurope)) |
   | `AZURE_RESOURCE_GROUP` | Resource group name |
   | `TF_STATE_*` | Remote-state storage account/container/key |

### The prod-name safety refusal

The script inspects the subscription name and **refuses to proceed if it
contains "prod"**. This is a deliberate, blunt guard: the platform is a
demo, its workflows include a destroy path, and the cheapest time to prevent
a production accident is before federation exists. If you legitimately need
to deploy near production naming, that decision deserves editing the script
consciously, not a flag.

## Two-stage deploy: `deploy-dev.yml`

A fresh environment has a chicken-and-egg problem: Container Apps need
images, images need a registry, and the registry is itself Terraform-managed.
The workflow resolves it in two Terraform passes:

1. **Foundation apply.** Terraform creates everything that does not need an
   image: resource group, ACR, PostgreSQL Flexible Server + PostGIS, storage
   (queues, blobs), Key Vault, Log Analytics + Application Insights, managed
   identity.
2. **Image build.** `az acr build` builds the api, worker, and web images in
   the (now existing) registry, tagged with the **git SHA** — so every
   running container is traceable to an exact commit, and rollback is
   redeploying an older SHA ([operations.md](operations.md#roll-back-an-image)).
3. **Workloads apply.** Terraform applies again with the image tags,
   creating/updating the Container Apps and Jobs.

The workflow then runs the **database migration job** and **smoke tests**
against the live environment.

## Manual Terraform usage

For infra iteration outside CI (still using the remote state created by
bootstrap):

```bash
cd infra
terraform init \
  -backend-config="resource_group_name=$TF_STATE_RESOURCE_GROUP" \
  -backend-config="storage_account_name=$TF_STATE_STORAGE_ACCOUNT" \
  -backend-config="container_name=$TF_STATE_CONTAINER" \
  -backend-config="key=$TF_STATE_KEY"
terraform plan
terraform apply
```

Rules of engagement:

- Authenticate as yourself (`az login`); never mint long-lived credentials.
- Always plan before apply; CI and manual runs share one state, so a manual
  apply diverging from `main` will be reverted by the next CI deploy.
- Destroy only through the `destroy-dev` workflow (typed confirmation), not
  `terraform destroy` ad hoc
  ([operations.md](operations.md#destroy-the-dev-environment-safely)).

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `AADSTS700016` / `No matching federated identity record found` during login | OIDC **subject mismatch**: the workflow runs from a different repo, branch, or environment than the federated credential expects (subject looks like `repo:raveheart1/Orbital-Earth-Observation-Platform:environment:dev`) | Ensure the job uses `environment: dev` and runs in this repo; compare the federated credential subject in Azure AD with the workflow context; re-run bootstrap after renames |
| `AuthorizationFailed` on specific resources during apply | Missing **role assignments** for the federated identity (or propagation delay right after bootstrap) | Verify assignments on the subscription/RG scope; role assignments can take a few minutes to propagate — retry before escalating |
| ACR push denied during `az acr build` | Identity lacks ACR roles, or the registry was created in a different pass than expected | Check `AcrPush` on the registry; confirm stage 1 completed |
| Quota / SKU errors creating PostgreSQL or Container Apps | Regional capacity or subscription **quota** limits | Try another region (`AZURE_LOCATION`), request a quota increase, or pick an available SKU; B-series PG capacity varies by region |
| Terraform state lock errors | A previous run crashed holding the blob lease | Confirm no run is active, then break the lease on the state blob |
| First workload apply fails to find images | Stage ordering: images not yet built for this SHA | Re-run the workflow; verify the `az acr build` step succeeded and tags match the SHA Terraform received |
