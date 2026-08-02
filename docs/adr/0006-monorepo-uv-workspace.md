# ADR 0006: Monorepo with a uv workspace

Status: accepted

## Context

The system spans a science library, a platform library, two Python services,
a Next.js app, infrastructure, and notebooks. Separate repositories would
require versioning and publishing internal packages to share code — heavy
ceremony for a system whose components always ship together. The science
code must also be importable outside the services (notebooks, tests) without
dragging in database or Azure dependencies.

## Decision

One repository, structured as a **uv workspace** (Python 3.12) with two
libraries and two apps: `packages/earth_observation` (science, no DB/Azure
deps), `packages/platform_core` (imported as `oeop_core`: settings, DB,
Azure, logging), `apps/api`, `apps/worker` — plus `apps/web` (pnpm),
`infra/`, `notebooks/`, and `scripts/`. A single `uv.lock` pins every Python
dependency across all members; its sha256 is recorded in each provenance
document. Make targets (`bootstrap`, `dev`, `test`, `lint`, `typecheck`,
`verify`, ...) operate on the whole workspace.

## Consequences

- Cross-cutting changes (schema + API + worker + docs) land as one reviewed
  commit; images built from one SHA are mutually consistent.
- The dependency boundary is enforced by packaging: `earth_observation`
  cannot silently grow platform dependencies, which keeps the notebook path
  honest (`notebooks/ndvi_southeast_michigan.ipynb` imports the exact
  production science code).
- One lockfile means one resolved version set — deliberate, for
  reproducibility, at the cost of per-app dependency freedom.
- CI must be path-aware to stay fast as the repo grows; acceptable at
  current size.
