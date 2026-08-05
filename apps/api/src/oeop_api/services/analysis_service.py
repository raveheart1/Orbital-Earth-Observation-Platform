"""Analysis submission: validation, constraint enforcement, persistence, enqueue.

The queue message is sent only AFTER the database transaction commits, so a
worker can never observe a message without its analysis record. If the
enqueue itself fails, the committed record is marked failed (queued-but-lost
records are also recoverable via the admin ``requeue`` command).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import anyio
from geoalchemy2.shape import from_shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from earth_observation import PROCESSING_VERSION
from earth_observation.errors import UserInputError
from earth_observation.geometry import bbox_polygon, geodesic_area_km2, validate_bbox
from earth_observation.types import ProcessingConfig
from oeop_api.problem import ProblemException
from oeop_api.schemas import AnalysisCreateRequest
from oeop_core.azure.queue import AnalysisQueue
from oeop_core.db.models import Analysis, AnalysisStatus, FailureCategory, Region
from oeop_core.logging import get_logger
from oeop_core.settings import Settings

logger = get_logger(__name__)


async def resolve_region(session: AsyncSession, region_id: uuid.UUID) -> Region:
    region = await session.get(Region, region_id)
    if region is None:
        raise ProblemException(404, "Region not found", f"No region with id {region_id}")
    return region


def _validate_dates(request: AnalysisCreateRequest, settings: Settings) -> None:
    if request.end_date < request.start_date:
        raise UserInputError("end_date must be on or after start_date")
    if request.start_date < settings.min_start_date:
        raise UserInputError(
            f"start_date must be {settings.min_start_date.isoformat()} or later "
            "(archive availability)"
        )
    today = datetime.now(UTC).date()
    if request.start_date > today:
        raise UserInputError("start_date cannot be in the future")
    span = (request.end_date - request.start_date).days
    max_span = settings.effective_max_date_span_days()
    if span > max_span:
        raise UserInputError(
            f"Requested date span of {span} days exceeds the maximum of {max_span} days"
        )


def _validate_scene_limit(request: AnalysisCreateRequest, settings: Settings) -> int:
    limit = request.scene_limit or settings.default_scene_limit
    max_limit = settings.effective_max_scene_limit()
    if limit > max_limit:
        raise UserInputError(f"scene_limit exceeds the server maximum of {max_limit}")
    return limit


async def create_analysis(
    *,
    session: AsyncSession,
    queue: AnalysisQueue,
    settings: Settings,
    request: AnalysisCreateRequest,
    is_demo: bool = False,
) -> Analysis:
    if not settings.submissions_enabled:
        raise ProblemException(
            503,
            "Submissions temporarily disabled",
            "New analyses are currently disabled. Precomputed results remain available.",
        )
    if (request.region_id is None) == (request.bbox is None):
        raise UserInputError("Provide exactly one of region_id or bbox")

    region: Region | None = None
    if request.region_id is not None:
        region = await resolve_region(session, request.region_id)
        bbox = validate_bbox(tuple(region.bbox))
    else:
        assert request.bbox is not None
        if not settings.allow_custom_areas:
            raise ProblemException(
                403,
                "Custom areas are disabled",
                "This deployment only accepts analyses over predefined regions. "
                "Select a region instead of drawing a custom area.",
            )
        bbox = validate_bbox(request.bbox)

    polygon = bbox_polygon(bbox)
    area_km2 = geodesic_area_km2(polygon)
    # Predefined regions are curated and run at ~137 km²; visitor-drawn areas
    # are held to a much tighter ceiling so arbitrary public submissions stay
    # cheap to process.
    is_custom_area = region is None
    max_area = (
        settings.effective_max_custom_aoi_area_km2()
        if is_custom_area
        else settings.effective_max_aoi_area_km2()
    )
    if area_km2 > max_area:
        detail = (
            f"Drawn area of {area_km2:.2f} km² exceeds the maximum of "
            f"{max_area:g} km² for custom areas. Draw a smaller box, or choose a "
            "predefined region to analyse a larger area."
            if is_custom_area
            else f"AOI area of {area_km2:.1f} km² exceeds the maximum of {max_area:.0f} km²"
        )
        raise UserInputError(detail)
    if area_km2 < settings.min_aoi_area_km2:
        raise UserInputError(
            f"AOI area of {area_km2:.2f} km² is below the minimum of "
            f"{settings.min_aoi_area_km2} km²"
        )

    _validate_dates(request, settings)
    scene_limit = _validate_scene_limit(request, settings)
    if request.max_cloud_cover_pct > settings.max_cloud_cover_pct:
        raise UserInputError(
            f"max_cloud_cover_pct exceeds the server maximum of {settings.max_cloud_cover_pct}"
        )

    config = ProcessingConfig(preview_max_dim=settings.preview_max_dim)
    analysis = Analysis(
        region_id=region.id if region else None,
        geometry=None if region else from_shape(polygon, srid=4326),
        bbox=list(bbox),
        area_km2=area_km2,
        start_date=request.start_date,
        end_date=request.end_date,
        collection=config.collection,
        max_cloud_cover_pct=request.max_cloud_cover_pct,
        scene_limit=scene_limit,
        operation="ndvi",
        processing_config=config.model_dump(),
        processing_version=PROCESSING_VERSION,
        git_commit_sha=settings.git_commit_sha,
        status=AnalysisStatus.QUEUED,
        is_demo=is_demo,
    )
    session.add(analysis)
    await session.commit()
    await session.refresh(analysis)

    try:
        await anyio.to_thread.run_sync(queue.send_analysis, str(analysis.id))
    except Exception as exc:
        logger.error("enqueue_failed", analysis_id=str(analysis.id), error=str(exc))
        analysis.status = AnalysisStatus.FAILED
        analysis.failure_category = FailureCategory.TRANSIENT
        analysis.failure_detail = "Failed to enqueue processing job; requeue via admin CLI."
        await session.commit()
        raise ProblemException(
            503,
            "Queue unavailable",
            "The analysis was recorded but could not be queued. It can be requeued by an operator.",
        ) from exc

    logger.info(
        "analysis_submitted",
        analysis_id=str(analysis.id),
        area_km2=round(area_km2, 2),
        start=request.start_date.isoformat(),
        end=request.end_date.isoformat(),
        scene_limit=scene_limit,
    )
    return analysis


async def get_demo_analysis_id(session: AsyncSession) -> uuid.UUID | None:
    result = await session.execute(
        select(Analysis.id)
        .where(Analysis.is_demo.is_(True), Analysis.status == AnalysisStatus.SUCCEEDED)
        .order_by(Analysis.submitted_at.desc())
        .limit(1)
    )
    row = result.first()
    return row[0] if row else None


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise UserInputError(f"Invalid date: {value}") from exc
