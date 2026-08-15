# AGENTS.md

Guidance for AI agents and contributors working in this repository.

## Project goal

The Orbital Earth Observation Platform answers one question: **how has
vegetation health changed at a given place over time, based on Sentinel-2
satellite observations?** — with a companion for fire-affected areas: **how
strongly did the burn signature (NBR) change?** It turns those questions into
auditable measurements —
STAC discovery via Microsoft Planetary Computer, documented cloud masking,
NDVI or NBR over user-selected AOIs, and machine-readable provenance (STAC item IDs,
mask policy, software versions, SHA-256 of every output) for each analysis.

Keep every change aligned with that goal: real data only, reproducible,
auditable. No synthetic or fabricated results in production paths (enforced by
`tests/test_no_synthetic_data_in_production.py`).

## Layout

```
apps/          api (FastAPI), worker (queue consumer), web (Next.js)
packages/      earth_observation (science core), platform_core (settings/db/azure)
infra/         Terraform modules + dev environment
docs/          methodology, provenance, architecture, operations, ADRs
scripts/       operational scripts (demo, smoke test, bootstrap)
data/demo/     committed demonstration bundle
tests/         cross-cutting integration tests
```

## Commands (see Makefile)

- `make bootstrap` — install Python (uv) + web (pnpm) deps, create `.env`
- `make dev` — build & start the full local stack (PostGIS, Azurite, API, worker, web)
- `make migrate` / `make seed` — database migrations / predefined regions
- `make test` — Python suite (no services needed); `make web-test` — vitest
- `make lint` — ruff format+lint, web lint; `make typecheck` — mypy + tsc
- `make verify` — complete local validation suite (run before shipping)

## Conventions

- Python: managed with **uv**; lint/format with **ruff**; types with **mypy**.
  Tests use synthetic rasters with analytically known NDVI — never live data.
- Web: Next.js + TypeScript (strict), **pnpm**, vitest unit tests.
- Database: SQLAlchemy enums use `native_enum=False` (stored as VARCHAR), so
  adding enum members needs no Alembic migration; column changes do
  (`apps/api/alembic/versions/`).
- Errors are RFC 7807 `application/problem+json`; document new ones in
  `docs/api-errors.md`.
- Provenance documents are validated against a published schema in
  `docs/schemas/` — bump the schema version and keep docs in sync when the
  provenance payload changes.
- Minimal, reviewable diffs. Match the surrounding code style; do not refactor
  beyond the task. Update `README.md`/docs when behavior or commands change.
- Do not commit secrets; `.env` is gitignored and gitleaks runs in CI.
