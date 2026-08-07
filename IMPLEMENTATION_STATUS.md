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

## Global repositioning and region catalog (2026-08-05)

- [x] **Custom-area cap raised 2 -> 250 km²**, chosen from measured cost rather
      than guessed: outputs run **~0.06 MB per scene per km²**, so the 200 MB
      per-analysis storage cap binds near **417 km² at 8 scenes** and 278 km²
      at 12. Runtime is ~10-12 s per scene at 137 km², nowhere near the 1500 s
      cap, so storage is the binding constraint. 250 km² keeps margin and
      matches the curated regions' ceiling, so users see one number.
- [x] **Repositioned as global with a Michigan focus.** Verified before
      advertising: the canonical grid selects correct UTM zones across Egypt,
      Brazil, Botswana, Vietnam, California, Spain and both hemispheres, and
      multi-tile mosaicking works abroad (the Nile Delta AOI spans **three**
      Sentinel-2 tiles). Coverage is stated honestly as roughly 56°S-83°N.
- [x] **Region catalog 4 -> 10**, each ~137 km² so cost is comparable:
      4 Michigan (home focus) plus Nile Delta, Amazon deforestation frontier,
      Central Valley, Okavango Delta, Mekong Delta and Doñana — five continents
      and both hemispheres.
- [x] **Every region has a real showcase analysis** (6 scenes each, live
      Sentinel-2 imagery, nothing precomputed), via the new idempotent
      `scripts/seed_showcase.sh`. NDVI ranges are physically sensible per
      biome: conifer forest 0.46-0.81, dune/water 0.08-0.30, Mediterranean
      wetland 0.19-0.61, rice 0.42-0.69.
- [x] Corrected stale documentation found during the sweep: the date-span and
      earliest-start limits still quoted the pre-multi-year values, and
      `.env.example` still pinned the custom cap at 2 km².

## Published case study and the audit behind it (2026-08-06)

- [x] **`docs/case-study.md`** (~5,200 words) and a short
      **`docs/case-study-linkedin.md`** (~1,150 words), both rendered to PDF by
      `scripts/build_case_study_pdf.py` using the Chromium that Playwright
      already installs for the end-to-end tests.
- [x] **Adversarially fact-checked before publication.** Four review lenses
      (numbers, science, repo-truth, editorial) produced 66 candidate findings;
      each was then handed to an independent verifier instructed to refute it.
      19 survived, and all were fixed. Notable corrections:
      - "AOI pixels per observation" quoted 1,442,584 — the canonical grid's
        cell count — where the AOI mask is 1,367,491. The mask count is the
        denominator every statistic actually uses, and 1,367,491 x 100 m² is
        exactly the 136.75 km² stated two rows above.
      - The multi-year example cited a run that is not in the repository. It is
        now the recorded Detroit seasonal analysis (2018-2026, 2022 absent,
        mean NDVI 0.346-0.393, first-to-last +0.017).
      - Artifact count was 22; provenance records 26 outputs (50.2 MB).
      - Retry semantics were stated backwards: deterministic failures are
        recorded terminally and the message is deleted, never poisoned.
      - Reflectance scaling is resolved per *acquisition* from the dominant
        baseline, not per granule.
      - `each ~137 km²` was untrue of Hartwick Pines Forest (84 km²); corrected
        here, in `README.md`, and in the `regions.json` comment.
- [x] **A real defect the audit surfaced:** `_run_pipeline` computed
      `analysis_warnings` — including "the catalog search hit its per-window
      cap, so more acquisitions may exist" — and built the `SceneSearchResult`
      metadata, then called `build_provenance()` without either keyword. The
      provenance document therefore advertised an empty `warnings` array while
      the worker knew the result might be incomplete. Both are now persisted,
      guarded by a test that fails if the keywords are dropped again.

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
      web https://oeop.net (custom domain, Azure-managed TLS; the generated
      host ca-oeop-dev-web.politeriver-f001c624.eastus2.azurecontainerapps.io
      still answers)
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

## Custom domain and deploy stability (2026-08-06)

- [x] **The platform serves on https://oeop.net** with a free Azure-managed
      certificate (DigiCert, CN=oeop.net, auto-renewing). Apex A record to the
      environment's static IP plus the `asuid` TXT, both unproxied in
      Cloudflare so Azure can validate.
- [x] **Fixed: every push took the site down.** Stage 1 of `deploy-dev` ran
      `terraform apply -var deploy_workloads=false` unconditionally, and the
      apps are `count = var.deploy_workloads ? 1 : 0` — so it destroyed them
      and stage 2 recreated them. Found while investigating the domain: ARM
      reported the container apps did not exist while their URLs served 404s.
      Stage 1 now runs only when there is no registry in the Terraform state,
      the fresh-environment case it was written for. Verified by polling
      through two full deploys: 200 throughout, and `0 to destroy`.
- [x] Azure's ordering for a custom domain cannot be one Terraform apply: a
      managed certificate cannot be issued for a hostname that is not already
      on an app (`RequireCustomHostnameInEnvironment`), and the binding cannot
      reference a certificate that does not exist. The hostname is registered
      with TLS disabled, the certificate is issued against it, and the deploy
      workflow attaches the two with `az containerapp hostname bind`. The
      binding ignores changes to its certificate fields, or the next apply
      would strip the certificate off. Verified idempotent across a second
      deploy: binding intact, one certificate, no duplicates.
- [x] **`www.oeop.net` redirects to the apex** with a 301, path and query
      string preserved (`/analyses?x=1` -> `https://oeop.net/analyses?x=1`).
      Applied via `scripts/cloudflare_redirect_rule.py` rather than clicked, so
      the rule is recorded here. Until it existed, www returned 525: a redirect
      rule answers at Cloudflare's edge, so reaching the origin at all proved
      no rule matched, and Azure holds no certificate for that name because
      only the apex is bound.
- [x] Corrected in the same pass: the Cloudflare API token permission governing
      Redirect Rules is **Single Redirect**, not "Dynamic Redirect" as the
      runbook first said. The ruleset phase is still named
      `http_request_dynamic_redirect`; the two disagree in Cloudflare's own
      product.
