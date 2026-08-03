# syntax=docker/dockerfile:1.7
# Worker image. Build context: repository root (the uv workspace).
#   docker build -f apps/worker/Dockerfile --build-arg GIT_SHA=$(git rev-parse HEAD) .

# --- Builder ----------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/earth_observation/pyproject.toml packages/earth_observation/pyproject.toml
COPY packages/platform_core/pyproject.toml packages/platform_core/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-workspace --package oeop-worker

COPY packages packages
COPY apps/worker apps/worker
RUN uv sync --frozen --no-dev --no-editable --package oeop-worker

# --- Runtime ----------------------------------------------------------------
FROM python:3.12-slim-bookworm

ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="oeop-worker" \
      org.opencontainers.image.description="Orbital Earth Observation Platform NDVI processing worker" \
      org.opencontainers.image.source="https://github.com/raveheart1/Orbital-Earth-Observation-Platform" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.licenses="MIT"

# libexpat1 is required by the rasterio/GDAL wheels and absent from slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 app && useradd --uid 1000 --gid app --no-create-home app

WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
# Lockfile kept for provenance (dependency_lock_sha256 in provenance documents).
COPY --chown=app:app uv.lock /app/uv.lock

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OEOP_GIT_COMMIT_SHA="${GIT_SHA}"

USER app

# SIGTERM triggers graceful shutdown (finishes the in-flight analysis).
CMD ["oeop-worker"]
