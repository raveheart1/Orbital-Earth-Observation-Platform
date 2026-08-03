"""ORM -> API schema serialization."""

from __future__ import annotations

import json
from typing import Any

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping

from oeop_api.schemas import (
    AnalysisGrid,
    AnalysisLinks,
    AnalysisResponse,
    FailureInfo,
    ProcessingInfo,
    RegionResponse,
    SceneResponse,
    TimeseriesPoint,
)
from oeop_core.db.models import Analysis, Observation, Region, Scene


def geometry_to_geojson(geometry: Any) -> dict[str, Any] | None:
    if geometry is None:
        return None
    geojson: dict[str, Any] = json.loads(json.dumps(mapping(to_shape(geometry))))
    return geojson


def serialize_region(region: Region) -> RegionResponse:
    return RegionResponse(
        id=region.id,
        name=region.name,
        slug=region.slug,
        description=region.description,
        bbox=list(region.bbox),
        geometry=geometry_to_geojson(region.geometry) or {},
        area_km2=round(region.area_km2, 2),
        is_predefined=region.is_predefined,
    )


def serialize_analysis(analysis: Analysis, *, region: Region | None) -> AnalysisResponse:
    base = f"/api/v1/analyses/{analysis.id}"
    failure = None
    if analysis.failure_category is not None:
        failure = FailureInfo(
            category=analysis.failure_category.value,
            detail=analysis.failure_detail,
        )
    return AnalysisResponse(
        id=analysis.id,
        status=analysis.status.value,  # type: ignore[arg-type]
        status_message=analysis.status_message,
        region=serialize_region(region) if region else None,
        bbox=list(analysis.bbox),
        geometry=geometry_to_geojson(analysis.geometry),
        area_km2=round(analysis.area_km2, 2),
        start_date=analysis.start_date,
        end_date=analysis.end_date,
        collection=analysis.collection,
        max_cloud_cover_pct=analysis.max_cloud_cover_pct,
        scene_limit=analysis.scene_limit,
        processing=ProcessingInfo(
            operation=analysis.operation,
            version=analysis.processing_version,
            git_commit_sha=analysis.git_commit_sha,
        ),
        submitted_at=analysis.submitted_at,
        started_at=analysis.started_at,
        completed_at=analysis.completed_at,
        failure=failure,
        retry_count=analysis.retry_count,
        summary=analysis.summary,
        grid=AnalysisGrid(**analysis.grid) if analysis.grid else None,
        is_demo=analysis.is_demo,
        links=AnalysisLinks(
            self=base,
            scenes=f"{base}/scenes",
            timeseries=f"{base}/timeseries",
            artifacts=f"{base}/artifacts",
            provenance=f"{base}/provenance",
        ),
    )


def serialize_scene(scene: Scene) -> SceneResponse:
    return SceneResponse(
        id=scene.id,
        stac_collection=scene.stac_collection,
        stac_item_id=scene.stac_item_id,
        acquisition_key=scene.acquisition_key,
        contributing_item_ids=list(scene.contributing_item_ids or [scene.stac_item_id]),
        tile_ids=list(scene.tile_ids or []),
        granule_count=scene.granule_count,
        aoi_coverage_pct=scene.aoi_coverage_pct,
        valid_pixel_pct=scene.valid_pixel_pct,
        observed_at=scene.observed_at,
        cloud_cover_pct=scene.cloud_cover_pct,
        platform=scene.platform,
        instruments=scene.instruments,
        selection_status=scene.selection_status.value,  # type: ignore[arg-type]
        exclusion_reason=scene.exclusion_reason,
        source_provider=scene.source_provider,
        assets=scene.assets,
        quality=scene.quality,
        bbox=list(scene.bbox) if scene.bbox else None,
    )


def serialize_timeseries_point(observation: Observation, scene: Scene) -> TimeseriesPoint:
    return TimeseriesPoint(
        scene_id=scene.id,
        stac_item_id=scene.stac_item_id,
        observed_at=scene.observed_at,
        stac_cloud_cover_pct=scene.cloud_cover_pct,
        ndvi_min=observation.ndvi_min,
        ndvi_max=observation.ndvi_max,
        ndvi_mean=observation.ndvi_mean,
        ndvi_median=observation.ndvi_median,
        ndvi_std=observation.ndvi_std,
        ndvi_p10=observation.ndvi_p10,
        ndvi_p25=observation.ndvi_p25,
        ndvi_p75=observation.ndvi_p75,
        ndvi_p90=observation.ndvi_p90,
        valid_pixel_count=observation.valid_pixel_count,
        masked_pixel_count=observation.masked_pixel_count,
        valid_pixel_pct=observation.valid_pixel_pct,
        aoi_coverage_pct=observation.aoi_coverage_pct,
        valid_coverage_pct=observation.valid_coverage_pct,
        missing_data_pct=observation.missing_data_pct,
        granule_count=observation.granule_count,
        contributing_item_ids=list(scene.contributing_item_ids or [scene.stac_item_id]),
        tile_ids=list(scene.tile_ids or []),
    )
