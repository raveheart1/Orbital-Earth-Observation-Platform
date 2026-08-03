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

## Azure deployment (completed 2026-08-03, after explicit owner approval)

The initial build withheld deployment because the selected subscription
(`ScoreSage - Prod`) is production-named. The owner subsequently and
explicitly chose to deploy there; the bootstrap safety rail was overridden
with `OEOP_ALLOW_PROD=1`. Deployment creates only the isolated resource
groups `rg-oeop-bootstrap` and `rg-oeop-dev`.

- [x] Bootstrap: OIDC federation (classic + immutable subject formats),
      remote Terraform state, deployment identity and scoped roles,
      GitHub environment + variables.
- [x] Region: **eastus2** — the subscription is offer-restricted for
      PostgreSQL Flexible Server in eastus (`LocationIsOfferRestricted`).
- [x] `deploy-dev` workflow green end to end: foundation apply, three
      `az acr build` images tagged with the commit SHA, workload apply,
      migration job, region seeding, endpoint smoke tests.
- [x] Public endpoints healthy:
      web https://ca-oeop-dev-web.politeriver-f001c624.eastus2.azurecontainerapps.io
      · API https://ca-oeop-dev-api.politeriver-f001c624.eastus2.azurecontainerapps.io
- [x] Bounded cloud analysis succeeded (analysis
      96dc489d-9e67-4630-afbc-23098eab7f87): the KEDA queue-scaled job woke
      from zero and processed 3 real Sentinel-2 scenes; NDVI means match the
      local runs exactly (0.592 / 0.597 / 0.606). User-delegation SAS
      downloads and provenance (container image + git SHA) verified.

Issues found and fixed during deployment (committed):
1. GitHub's immutable OIDC subject format (owner/repo IDs embedded) —
   bootstrap now registers federated credentials for both formats.
2. eastus PostgreSQL offer restriction — location is now driven by the
   `AZURE_LOCATION` repository variable end to end.
3. Region-move tombstones: Key Vault purge requires a subscription-scoped
   role (now granted by bootstrap); PostgreSQL server names now embed the
   region because the RP reserves failed names against their location.
4. `az acr build` has no BuildKit — Dockerfile cache mounts removed.

## Blocked

- None.
