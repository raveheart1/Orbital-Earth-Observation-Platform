"""Liveness and readiness probes.

Readiness verifies the dependencies the API actually needs: the database and
the storage queue. Liveness never touches dependencies.
"""

from __future__ import annotations

import anyio
from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

from oeop_api.schemas import HealthResponse
from oeop_core.logging import get_logger

router = APIRouter(prefix="/health", tags=["health"])
logger = get_logger(__name__)


@router.get("/live", response_model=HealthResponse, summary="Liveness probe")
async def live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse, summary="Readiness probe")
async def ready(request: Request, response: Response) -> HealthResponse:
    checks: dict[str, str] = {}
    healthy = True

    try:
        factory = request.app.state.session_factory
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        healthy = False
        checks["database"] = "unavailable"
        logger.warning("readiness_database_failed", error=type(exc).__name__)

    try:
        queue = request.app.state.queue
        await anyio.to_thread.run_sync(queue.approximate_depth)
        checks["queue"] = "ok"
    except Exception as exc:
        healthy = False
        checks["queue"] = "unavailable"
        logger.warning("readiness_queue_failed", error=type(exc).__name__)

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="ok" if healthy else "degraded", checks=checks)
