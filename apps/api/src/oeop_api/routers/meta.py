"""Dataset catalog and public configuration endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from earth_observation import PROCESSING_VERSION
from earth_observation.previews import legend_spec
from earth_observation.stac import dataset_info
from earth_observation.types import ProcessingConfig
from oeop_api.deps import SessionDep, SettingsDep
from oeop_api.schemas import DatasetResponse, PublicConfigResponse
from oeop_api.services.analysis_service import get_demo_analysis_id

router = APIRouter(tags=["meta"])

#: Map default view: Southeast Michigan (center lon/lat + zoom).
MAP_DEFAULT_CENTER = (-83.15, 42.5)
MAP_DEFAULT_ZOOM = 8.5


@router.get("/datasets", response_model=list[DatasetResponse], summary="Datasets used")
async def list_datasets() -> list[DatasetResponse]:
    config = ProcessingConfig()
    info = dataset_info(config)
    return [DatasetResponse(**info)]  # type: ignore[arg-type]


@router.get(
    "/config/public",
    response_model=PublicConfigResponse,
    summary="Public limits and UI configuration",
)
async def public_config(settings: SettingsDep, session: SessionDep) -> PublicConfigResponse:
    config = ProcessingConfig()
    return PublicConfigResponse(
        environment=settings.environment,
        demo_mode=settings.demo_mode,
        submissions_enabled=settings.submissions_enabled,
        max_aoi_area_km2=settings.effective_max_aoi_area_km2(),
        min_aoi_area_km2=settings.min_aoi_area_km2,
        custom_areas_enabled=settings.allow_custom_areas,
        max_custom_aoi_area_km2=settings.effective_max_custom_aoi_area_km2(),
        max_date_span_days=settings.effective_max_date_span_days(),
        min_start_date=settings.min_start_date,
        max_scene_limit=settings.effective_max_scene_limit(),
        default_scene_limit=settings.default_scene_limit,
        max_cloud_cover_pct=settings.max_cloud_cover_pct,
        default_cloud_cover_pct=settings.default_cloud_cover_pct,
        map_default_center=MAP_DEFAULT_CENTER,
        map_default_zoom=MAP_DEFAULT_ZOOM,
        ndvi_legend=legend_spec(config.ndvi_display_min, config.ndvi_display_max),
        demo_analysis_id=await get_demo_analysis_id(session),
        processing_version=PROCESSING_VERSION,
    )
