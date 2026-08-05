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

## Spatial comparability fix (processing version 2.0.0, 2026-08-03)

An audit of the deployed Detroit Urban Core analysis
(`b4b9935e-5123-41e9-a58b-22a57811dc75`) found a genuine scientific defect,
not a display problem: the AOI straddles the T17TLG/T17TLH Sentinel-2 tile
boundary, and v1 selected ONE granule per date. Dates backed by T17TLH covered
only 56.2% of the AOI, producing 1272x627 rasters against 1272x1149 for
T17TLG dates, and NDVI statistics computed over 751,081 vs 1,372,771 pixels —
different ground. See
[docs/audit-2026-08-03-spatial-comparability.md](docs/audit-2026-08-03-spatial-comparability.md).

- [x] **Canonical analysis grid** per analysis (UTM CRS, 10 m, snapped
      bounds, fixed transform/size/AOI mask), persisted and echoed in
      provenance.
- [x] **Acquisition grouping + mosaicking**: granules of one acquisition are
      grouped by time/platform/orbit/collection and mosaicked onto the grid
      (bilinear spectral, nearest categorical SCL, deterministic overlap
      resolution).
- [x] **Coverage validation**: geometric/valid/masked/missing accounting per
      acquisition, configurable threshold (default 99%), with uncovered vs
      nodata vs cloud vs snow vs invalid distinguished.
- [x] **Identical analytical footprint** enforced; the worker refuses to
      publish an analysis whose observations disagree on their grid.
- [x] Previews on the canonical grid with identical dimensions, fixed legend
      range, and opaque grey for "no source imagery".
- [x] Frontend: fixed comparison viewport (no distortion), coverage/valid/
      granule metadata, AOI overlay, grid-mismatch alert, valid-pixel % in the
      scene table, acquisition dates labelled.
- [x] Provenance schema 2.0.0 with grid, coverage, and every contributing
      STAC item and tile id.
- [x] Regression tests with synthetic adjacent-granule fixtures (no network).
- [x] Demonstration bundle regenerated: all six observations now mosaic
      T16TGN + T17TLH **across a UTM zone boundary** onto one EPSG:32617 grid
      (v1 produced those in two different CRSs).

**Quantified impact:** reprocessing Detroit reproduced the full-coverage date
2026-02-27 exactly (0.1574), while the partial-coverage date 2026-05-30
corrected from 0.4233 to 0.3671 (-0.056). The previously reported -0.053
earliest-to-latest difference was not a valid measurement.

## Custom areas and drift guards (2026-08-04)

- [x] **Visitor-drawn areas enabled**, capped at **2 km²**
      (`OEOP_MAX_CUSTOM_AOI_AREA_KM2`, toggle `OEOP_ALLOW_CUSTOM_AREAS`).
      The cap applies ONLY to drawn areas — curated predefined regions still
      run at ~84–137 km² under `OEOP_MAX_AOI_AREA_KM2`. Enforced server-side
      in `create_analysis`, mirrored in the browser, and surfaced through
      `/api/v1/config/public`. A 0.9 km² area yields a 95 × 101 grid and
      completes in seconds.
- [x] **Fixed `scripts/live_smoke_test.py` and the notebook**, which still
      called the removed `select_scenes` / `process_scene` and had been broken
      since processing 2.0.0. The notebook was re-executed against live data,
      so its committed outputs now show canonical-grid results.
- [x] **Closed the gap that let that happen:** `scripts/` is now type-checked
      (mypy immediately found a latent `round(None)` bug), and
      `tests/test_public_api_drift.py` statically asserts every first-party
      symbol imported by `notebooks/` and `scripts/` still exists — no network
      needed, so it runs in CI.
- [x] **Deployed demo seeding:** `oeop-admin seed-demo --if-missing` is
      idempotent and now runs as part of the deployment seed job, so a fresh
      environment always has a completed demonstration analysis for the
      landing-page link. Previously `demo_analysis_id` was null in Azure.

## No-synthetic-data enforcement (2026-08-04)

An audit of what actually ships found that
`earth_observation.testing` — the synthetic Sentinel-2 raster generator — was
present inside the deployed API and worker images. No production code path
imported it, but its presence contradicted the platform's own rule that
synthetic imagery is permitted in automated tests only.

- [x] Excluded `testing.py` from the built wheel. Images install that wheel
      (`uv sync --no-editable`) so the module is physically absent; tests use
      the editable install and import it from `src/`, unaffected.
- [x] Verified against real artifacts: the built wheel contains 18 modules and
      no `testing.py`, and a rebuilt image confirms the same. The CI guard was
      sanity-checked by running it against the pre-fix image, where it
      correctly reports the violation.
- [x] Three enforcement layers: wheel exclusion,
      `tests/test_no_synthetic_data_in_production.py` (builds and inspects the
      wheel, and greps production sources for fixture imports/builders), and a
      CI step that inspects the built images.
- [x] Also confirmed clean: no test fixtures in the Next.js production bundle,
      no mock/fallback data anywhere in shipped frontend code, and `data/`
      (the demo bundle) is never copied into an image — deployed environments
      process live imagery.
- [x] README screenshots regenerated from the deployed Azure site.

## Multi-year analysis (2026-08-05)

Probing real data showed two problems that made long date ranges misleading,
so both were fixed before the span limit was raised.

- [x] **Catalog search was silently truncated.** A single STAC query is capped
      at `max_items` and returns catalog order, so requesting 2018–2026 over
      Detroit searched only **2022–2026** — four years presented as eight.
      Long ranges are now searched in consecutive windows (default 370 days)
      with the cap applied per window; the same request now returns 345
      granules spanning 2018-01-05 to 2026-06-27. Any window that hits its cap
      is recorded in provenance and raised as an analysis warning.
- [x] **Seasonal selection strategy** (`seasonal-same-window-lowest-cloud`
      v1.0.0): one observation per year from the same part of the calendar.
      The evenly-spread strategy over 8 years picked June, February, April,
      May, April, October, June, May — a "trend" from that is dominated by
      which month each scene fell in, since the seasonal NDVI swing
      (~0.15–0.85) is an order of magnitude larger than a multi-year trend.
      A year with nothing usable is left as a gap, never substituted.
- [x] **Span limit raised** 400 → **3660 days (~10 years)**, earliest start
      2015-07-01. Long spans cost no more to process: work is bounded by
      `scene_limit` and AOI area, and the extra search is metadata only.
- [x] Verified on real data: an 8.5-year seasonal Detroit analysis returned
      one early-July observation per year (2018–2026, 2022 absent), all on one
      canonical grid, mean NDVI 0.346–0.393, first-to-last **+0.017** — which
      is smaller than the year-to-year scatter and so is explicitly documented
      as not establishing a trend.
- [x] A leap-year off-by-one in the day-of-year wrap was found by the new
      tests and fixed (the window used a hardcoded 365-day year).

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
