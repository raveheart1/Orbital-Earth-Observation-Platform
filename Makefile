# Orbital Earth Observation Platform — developer entry points.
# Prerequisites: uv, docker (with compose v2), node 22+ with corepack/pnpm.
# Run `make bootstrap` once, then `make dev`.

SHELL := /bin/bash
TERRAFORM ?= terraform
COMPOSE ?= docker compose

.PHONY: help bootstrap dev migrate seed test lint typecheck live-smoke-test demo \
        verify down clean web-install web-build web-test screenshot

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Install Python + web dependencies, create .env from the example
	uv sync
	cd apps/web && pnpm install
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

dev: ## Build and start the full local stack (PostGIS, Azurite, API, worker, web)
	$(COMPOSE) up -d --build
	@echo ""
	@echo "  API:  http://localhost:8000/docs"
	@echo "  Web:  http://localhost:3000"
	@echo "  Next: make migrate && make seed"

migrate: ## Apply database migrations
	$(COMPOSE) run --rm migrate

seed: ## Seed predefined regions (idempotent)
	$(COMPOSE) run --rm --no-deps --entrypoint python migrate -m oeop_api.cli seed-regions

test: ## Run the Python test suite (no external services required)
	uv run pytest -q

web-install:
	cd apps/web && pnpm install

web-test: ## Run frontend unit tests
	cd apps/web && pnpm test

web-build: ## Production frontend build
	cd apps/web && pnpm build

lint: ## Ruff (format + lint) and web lint
	uv run ruff format --check .
	uv run ruff check .
	cd apps/web && pnpm lint

typecheck: ## mypy + TypeScript
	uv run mypy packages/earth_observation/src packages/platform_core/src apps/api/src apps/worker/src
	cd apps/web && pnpm typecheck

live-smoke-test: ## Process one REAL Sentinel-2 scene from the Planetary Computer (network)
	uv run python scripts/live_smoke_test.py

demo: ## Submit and wait for the demonstration analysis (stack must be running)
	./scripts/run_demo.sh

screenshot: ## Capture UI screenshots into docs/images (stack must be running)
	cd apps/web && pnpm exec playwright test e2e/screenshot.spec.ts

verify: ## The complete local validation suite
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy packages/earth_observation/src packages/platform_core/src apps/api/src apps/worker/src
	uv run pytest -q
	cd apps/web && pnpm lint && pnpm typecheck && pnpm test && pnpm build
	$(TERRAFORM) fmt -check -recursive infra
	cd infra/environments/dev && $(TERRAFORM) init -backend=false -input=false > /dev/null && $(TERRAFORM) validate
	$(COMPOSE) build
	@echo ""
	@echo "verify: all checks passed"

down: ## Stop the local stack (keeps data volumes)
	$(COMPOSE) down

clean: ## Stop the stack and delete volumes, caches, and build outputs
	$(COMPOSE) down -v --remove-orphans
	rm -rf .venv .mypy_cache .ruff_cache .pytest_cache apps/web/.next apps/web/node_modules data/local
