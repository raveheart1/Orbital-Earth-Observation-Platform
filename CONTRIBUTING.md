# Contributing

Thanks for considering a contribution. This document covers setup,
conventions, and expectations. The system itself is documented in
[`docs/`](docs/) — start with [architecture](docs/architecture.md) and the
[scientific methodology](docs/scientific-methodology.md).

## Development setup

Prerequisites:

- **Python 3.12** managed via [uv](https://docs.astral.sh/uv/) (the repo is a
  uv workspace with a single `uv.lock`)
- **pnpm** for the web app
- **Docker** with Compose (local PostGIS, Azurite, and the app containers)

No Azure account is needed for local development.

```bash
make bootstrap   # install toolchain + dependencies
make dev         # start the full local stack (postgis, azurite, api, worker, web)
make migrate     # apply database migrations
make seed        # load predefined regions
make demo        # run the demonstration analysis end to end
```

Other targets you will use constantly:

```bash
make test        # all test suites
make lint        # ruff (Python) + web lint
make typecheck   # mypy + strict TypeScript
make verify      # lint + typecheck + test — run before every PR
make live-smoke-test  # exercise the running local stack
make down        # stop containers
make clean       # remove containers/volumes/caches
```

## Repository layout

| Path | Contents |
| --- | --- |
| `packages/earth_observation` | Science core (STAC, selection, masking, NDVI, provenance). **No DB or Azure dependencies** — keep it that way. |
| `packages/platform_core` | Settings, DB models, Azure clients, logging, telemetry (imported as `oeop_core`). |
| `apps/api` | FastAPI service (`/api/v1`) and the `oeop-admin` CLI. |
| `apps/worker` | Queue consumer. |
| `apps/web` | Next.js 15 UI. |
| `infra/` | Terraform. |
| `docs/` | All documentation, ADRs, schemas. |
| `notebooks/` | Reproducible notebooks importing the science core. |

## Code style

- **Python:** ruff for linting/formatting, mypy for types. Type annotations
  are required; new `Any` needs a comment justifying it.
- **TypeScript:** strict mode; no `any` without justification.
- Errors must use the existing taxonomy
  (`earth_observation/errors.py`) — the worker's retry behavior depends on
  it. Never raise a bare `Exception` in pipeline code.
- Logs are structured (structlog): `logger.info("event_name", key=value)`,
  no f-string log messages, never log secrets or signed URLs.

`make lint` and `make typecheck` must pass; CI enforces both.

## Tests

- Unit tests live next to each package/app (`packages/*/tests`,
  `apps/*/tests`). Science code is tested against local synthetic rasters —
  tests must not hit the network (the signing function is injectable for
  exactly this reason).
- New behavior needs tests; bug fixes need a regression test that fails
  before the fix.
- Run `make verify` before opening a PR and include the result in the PR
  description.

## Science changes need methodology-doc updates

Anything that can change a scientific output is documentation-coupled.
If your change touches:

- the SCL mask policy, band scaling, NDVI math, or statistics →
  update [`docs/scientific-methodology.md`](docs/scientific-methodology.md)
- scene selection → update the methodology doc **and**
  [ADR 0003](docs/adr/0003-scene-selection-strategy.md); bump
  `SCENE_SELECTION_VERSION`
- the provenance document shape → bump the schema version, regenerate
  [`docs/schemas/provenance-1.0.0.json`](docs/schemas/provenance-1.0.0.json)
  (new version file), and update
  [`docs/data-provenance.md`](docs/data-provenance.md)
- result-affecting processing behavior → bump `PROCESSING_VERSION`

PRs changing science behavior without the corresponding doc change will be
sent back — the docs are part of the instrument.

## Commits and pull requests

- Small, focused commits with imperative subject lines
  ("Add SCL class table to methodology doc"), body explaining *why* when
  non-obvious.
- One logical change per PR. Fill in the PR template, including the
  science-impact checklist and `make verify` output.
- Architectural decisions (new dependencies with scientific impact, new
  infrastructure, changed reliability semantics) get an ADR in
  [`docs/adr/`](docs/adr/), numbered sequentially.

## Security

Do not open public issues for vulnerabilities — see [SECURITY.md](SECURITY.md).
