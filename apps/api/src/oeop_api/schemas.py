"""Public API request/response models (the versioned /api/v1 contract)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class AnalysisCreateRequest(BaseModel):
    """Submit a new NDVI analysis.

    Exactly one of ``region_id`` / ``bbox`` must be provided. ``bbox`` is
    ``[min_lon, min_lat, max_lon, max_lat]`` in WGS84.
    """

    model_config = ConfigDict(extra="forbid")

    region_id: uuid.UUID | None = None
    bbox: tuple[float, float, float, float] | None = None
    start_date: date
    end_date: date
    max_cloud_cover_pct: float = Field(default=20.0, ge=0.0, le=100.0)
    scene_limit: int | None = Field(default=None, ge=1)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class RegionResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str
    bbox: list[float]
    geometry: dict[str, Any]
    area_km2: float
    is_predefined: bool


class FailureInfo(BaseModel):
    category: str
    detail: str | None


class ProcessingInfo(BaseModel):
    operation: str
    version: str
    git_commit_sha: str | None


class AnalysisGrid(BaseModel):
    """The canonical analytical grid shared by every observation."""

    schema_version: str
    crs: str
    epsg: int | None = None
    resolution: list[float]
    transform: list[float]
    width: int
    height: int
    bounds_projected: list[float]
    bounds_geographic: list[float]
    signature: str


class AnalysisLinks(BaseModel):
    self: str
    scenes: str
    timeseries: str
    artifacts: str
    provenance: str


class AnalysisResponse(BaseModel):
    id: uuid.UUID
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    status_message: str | None
    region: RegionResponse | None
    bbox: list[float]
    geometry: dict[str, Any] | None
    area_km2: float
    start_date: date
    end_date: date
    collection: str
    max_cloud_cover_pct: float
    scene_limit: int
    processing: ProcessingInfo
    submitted_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure: FailureInfo | None
    retry_count: int
    summary: dict[str, Any] | None
    grid: AnalysisGrid | None = Field(
        default=None,
        description="Canonical analytical grid; null for legacy analyses processed "
        "before processing version 2.0.0",
    )
    is_demo: bool
    links: AnalysisLinks


class AnalysisListResponse(BaseModel):
    items: list[AnalysisResponse]
    total: int
    limit: int
    offset: int


class SceneResponse(BaseModel):
    id: uuid.UUID
    stac_collection: str
    stac_item_id: str = Field(description="Primary/representative granule of the acquisition")
    acquisition_key: str | None = None
    contributing_item_ids: list[str] = Field(
        default_factory=list,
        description="Every STAC item mosaicked into this observation",
    )
    tile_ids: list[str] = Field(default_factory=list)
    granule_count: int = 1
    aoi_coverage_pct: float | None = Field(
        default=None, description="Geometric AOI coverage by the source granules"
    )
    valid_pixel_pct: float | None = Field(
        default=None, description="Percent of AOI pixels usable after masking"
    )
    observed_at: datetime = Field(description="Acquisition (sensing) time, not processing time")
    cloud_cover_pct: float | None
    platform: str | None
    instruments: list[str] | None
    selection_status: Literal["selected", "excluded"]
    exclusion_reason: str | None
    source_provider: str
    assets: dict[str, Any] = Field(
        description="Original unsigned STAC asset hrefs, keyed by item id then role"
    )
    quality: dict[str, Any] | None
    bbox: list[float] | None


class TimeseriesPoint(BaseModel):
    scene_id: uuid.UUID
    stac_item_id: str
    observed_at: datetime
    stac_cloud_cover_pct: float | None
    ndvi_min: float | None
    ndvi_max: float | None
    ndvi_mean: float | None
    ndvi_median: float | None
    ndvi_std: float | None
    ndvi_p10: float | None
    ndvi_p25: float | None
    ndvi_p75: float | None
    ndvi_p90: float | None
    valid_pixel_count: int
    masked_pixel_count: int
    valid_pixel_pct: float
    aoi_coverage_pct: float | None = None
    valid_coverage_pct: float | None = None
    missing_data_pct: float | None = None
    granule_count: int = 1
    contributing_item_ids: list[str] = Field(default_factory=list)
    tile_ids: list[str] = Field(default_factory=list)


class TimeseriesResponse(BaseModel):
    analysis_id: uuid.UUID
    points: list[TimeseriesPoint]


class ArtifactResponse(BaseModel):
    id: uuid.UUID
    scene_id: uuid.UUID | None
    stac_item_id: str | None
    artifact_type: str
    content_type: str
    size_bytes: int
    sha256: str
    crs: str | None
    created_at: datetime
    grid_signature: str | None = Field(
        default=None,
        description="Analytical grid identity; artifacts of one analysis must match",
    )
    download_url: str = Field(description="Short-lived signed URL; regenerate by re-fetching")
    download_url_expires_in_seconds: int


class ArtifactListResponse(BaseModel):
    analysis_id: uuid.UUID
    items: list[ArtifactResponse]


class DatasetResponse(BaseModel):
    id: str
    title: str
    description: str
    stac_endpoint: str
    provider: str
    producer: str
    license: str
    assets_used: dict[str, str]
    gsd_meters: int


class PublicConfigResponse(BaseModel):
    environment: str
    demo_mode: bool
    submissions_enabled: bool
    max_aoi_area_km2: float
    min_aoi_area_km2: float
    max_date_span_days: int
    min_start_date: date
    max_scene_limit: int
    default_scene_limit: int
    max_cloud_cover_pct: float
    default_cloud_cover_pct: float
    map_default_center: tuple[float, float]
    map_default_zoom: float
    ndvi_legend: dict[str, Any]
    demo_analysis_id: uuid.UUID | None
    processing_version: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, str] = Field(default_factory=dict)
