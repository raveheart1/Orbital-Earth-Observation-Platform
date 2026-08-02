# ADR 0005: Managed identity and GitHub OIDC — no client secrets

Status: accepted

## Context

The system needs two credential paths: CI/CD deploying to Azure, and
workloads accessing Storage and Key Vault. The traditional approach — a
service principal client secret in GitHub secrets, connection strings in app
config — creates long-lived credentials that leak, expire at the worst
moment, and demand rotation discipline no demo project sustains.

## Decision

Zero client secrets:

- **CI/CD:** GitHub Actions authenticates via **OIDC federation**. Azure AD
  trusts tokens whose subject matches this repository and the `dev`
  environment; credentials are minted per run and expire in minutes.
  Bootstrap is scripted (`scripts/bootstrap-azure-github.sh`), which also
  refuses subscriptions with "prod" in the name.
- **Workloads:** a **user-assigned managed identity** grants Container Apps
  access to blobs, queues, and Key Vault. Blob downloads use
  **user-delegation SAS** (derived from that identity) rather than account
  keys.
- **Local dev** intentionally differs: Azurite with its well-known emulator
  connection string, account-key SAS — no Azure account required.

The remaining secret is the PostgreSQL password, held in Key Vault with a
documented rotation procedure
([operations.md](../operations.md#rotate-the-postgresql-password)).

## Consequences

- Nothing to rotate for deploy or storage access; nothing in GitHub secrets
  worth stealing.
- Failure modes shift from "leaked key" to "misconfigured trust": OIDC
  subject mismatches are the top deployment issue and are documented in
  [deployment.md](../deployment.md#troubleshooting).
- Code paths differ slightly between local (connection string) and Azure
  (identity) — abstracted in `oeop_core.azure` so app code is unaware.
- Provider lock-in at the auth layer is accepted; the science core has no
  Azure dependency at all.
