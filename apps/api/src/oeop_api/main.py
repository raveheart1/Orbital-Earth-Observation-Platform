"""FastAPI application factory.

Startup wires settings, the async engine, storage clients, structured
logging, and telemetry. Middleware adds request IDs, security headers, a
request-size limit, and restricted CORS.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import anyio
import structlog
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from oeop_api import API_VERSION
from oeop_api.problem import register_exception_handlers
from oeop_api.rate_limit import SubmissionRateLimiter
from oeop_api.routers import analyses, health, meta, regions
from oeop_core.azure.blob import BlobStore
from oeop_core.azure.queue import AnalysisQueue
from oeop_core.db.session import create_engine, create_session_factory
from oeop_core.logging import configure_logging, get_logger
from oeop_core.settings import Settings, get_settings
from oeop_core.telemetry import setup_telemetry

logger = get_logger(__name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, service="oeop-api")
    setup_telemetry("oeop-api", settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.engine = create_engine(settings)
        app.state.session_factory = create_session_factory(app.state.engine)
        app.state.blob_store = BlobStore(settings)
        app.state.queue = AnalysisQueue(settings)
        app.state.rate_limiter = SubmissionRateLimiter(settings.rate_limit_submissions_per_hour)
        # Local convenience: make sure containers/queues exist (idempotent).
        if settings.environment == "local":
            await anyio.to_thread.run_sync(app.state.blob_store.ensure_container)
            await anyio.to_thread.run_sync(app.state.queue.ensure_queues)
        logger.info("api_started", version=API_VERSION, environment=settings.environment)
        yield
        await app.state.engine.dispose()

    app = FastAPI(
        title="Orbital Earth Observation Platform API",
        version=API_VERSION,
        description=(
            "Sentinel-2 NDVI analyses over Michigan areas of interest. "
            "Results are observed vegetation-index measurements with full "
            "provenance; see /api/v1/datasets and the project documentation "
            "for methodology and limitations."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > settings.max_request_body_bytes:
                return JSONResponse(
                    {
                        "type": "about:blank",
                        "title": "Payload too large",
                        "status": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        "detail": "Request body exceeds the size limit.",
                    },
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    media_type="application/problem+json",
                )
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        response.headers["X-Request-ID"] = request_id
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
        max_age=600,
    )

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(analyses.router, prefix="/api/v1")
    app.include_router(regions.router, prefix="/api/v1")
    app.include_router(meta.router, prefix="/api/v1")
    return app


app = create_app()
