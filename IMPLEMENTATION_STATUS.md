# Implementation Status

Final status at the end of the initial build (2026-08-02). Honest accounting
of what is complete, partial, or blocked.

## Completed and verified

- [x] `packages/earth_observation` — STAC discovery, deterministic scene
      selection, SCL masking, baseline-aware reflectance scaling (including
      negative-reflectance clipping so NDVI stays in [−1, 1]), NDVI, COG +
      preview outputs, statistics, provenance schema + builder.
- [x] `packages/platform_core` — settings, PostGIS models, Azure blob/queue
      clients (Azurite + managed-identity modes), structured JSON logging,
      OpenTelemetry/Azure Monitor wiring.
- [x] `apps/api` — FastAPI `/api/v1` (analyses, scenes, timeseries,
      artifacts, provenance, regions, datasets, config, health), RFC 7807
      errors, rate limiting, security headers, admin CLI
      (seed-regions / seed-demo / requeue / queue-depth / export- & import-demo).
- [x] `apps/worker` — `--once`, `--analysis-id`, and poll modes; atomic
      claiming, idempotent reprocessing, visibility renewal, poison queue,
      failure taxonomy.
- [x] `apps/web` — Next.js 15 dashboard (MapLibre map + rectangle draw,
      Recharts NDVI time series with p25–p75 band, before/after previews,
      artifact downloads, provenance panel, accessibility states).
- [x] Alembic initial migration applies to a fresh PostGIS 16 database.
- [x] Docker images (api, worker, web) build; compose stack healthy end to
      end; `make verify` passes the complete local suite.
- [x] **Real-data demonstration analysis** over the Southeast Michigan
      Demonstration Region (Apr–Oct 2024, 6 Sentinel-2 scenes, seasonal NDVI
      0.385 → 0.606 → 0.580); bundle exported to `data/demo/` and re-import
      verified into a fresh database.
- [x] Live Planetary Computer smoke test passes (`make live-smoke-test`).
- [x] Notebook executed end to end against live data (outputs committed).
- [x] Terraform dev environment validates (azurerm 4.x); bootstrap script,
      CI (`ci.yml`), deploy (`deploy-dev.yml`, gated until bootstrap),
      `terraform-plan.yml`, `destroy-dev.yml` (manual + typed confirmation),
      Dependabot.
- [x] Documentation suite, ADRs, community files, screenshots, architecture
      diagram (Mermaid + SVG).
- [x] Pushed to GitHub
      (https://github.com/raveheart1/Orbital-Earth-Observation-Platform);
      CI fully green on main (python, web, terraform, 3× docker,
      secrets scan); `deploy-dev` skips cleanly until Azure bootstrap runs;
      branch protection on `main` requires the seven CI checks via PR.
      Note: the working directory carried a pre-existing remote to an empty
      private repo `ScoreSage/Orbital-Earth-Observation-Platform`; it is
      preserved as the `scoresage` remote, while `origin` is the public
      user-owned repository the build brief specified.
- [x] Test totals: **109 Python tests** (science, platform, API, worker;
      +6 stack-integration tests that run when the compose stack is up),
      **48 frontend tests**, 3 Playwright e2e/screenshot specs.

## Known limitations (accepted for MVP, documented)

- Submission rate limiting is in-memory per replica (docs/security.md).
- The public demo API has no authentication; abuse controls are the
  DEMO_MODE flag, tight server-side limits, and the submissions kill switch.
- `terraform plan` for PRs runs static checks only unless the PR is from the
  same repository (fork-credential safety; documented in the workflow).

## Blocked

- **Azure deployment — deliberately not executed (safety rule).** The
  currently selected Azure subscription is `ScoreSage - Prod`
  (7b5cf7e8-eeed-48cb-be16-831ee5cff535, tenant
  13079765-18cb-4305-821b-1321446fc628). The build brief forbids automatic
  deployment when the selected subscription clearly indicates a production
  environment, and this account also has access to many third-party client
  subscriptions, so no subscription switch was made autonomously.
  - Everything needed to deploy is committed: Terraform for the full dev
    environment, `scripts/bootstrap-azure-github.sh` (OIDC federation,
    remote state, GitHub environment + variables), and `deploy-dev.yml`
    (every job is gated on `vars.AZURE_CLIENT_ID != ''`, so pushes to main
    skip deployment cleanly until bootstrap has been run).
  - Remediation:
    1. `az account set --subscription "<a non-production subscription>"`
    2. `./scripts/bootstrap-azure-github.sh` (refuses subscriptions with
       "prod" in the name unless `OEOP_ALLOW_PROD=1`)
    3. Re-run the "Deploy dev" workflow (or push to main).
  - Blocked acceptance criteria as a result: OIDC federation configured,
    remote state initialized, dev infrastructure deployed, images in ACR,
    cloud migrations, Container Apps health, public URLs, bounded cloud
    analysis, GitHub deployment variables. All are exercised by the deploy
    workflow once bootstrap runs.
