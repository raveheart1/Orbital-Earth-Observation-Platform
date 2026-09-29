"""Public API request/response models (the versioned /api/v1 contract)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class TemporalContextRequest(BaseModel):
    """Optional temporal context for a time-series analysis."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    baseline_years: int = Field(
        default=5,
        ge=1,
        description="Full calendar years before the analysis start year used as the "
        "seasonal reference period; capped by /api/v1/config/public",
    )


class WildfireRequest(BaseModel):
    """Pre/post-fire windows and severity interpretation for workflow=wildfire_dnbr."""

    model_config = ConfigDict(extra="forbid")

    pre_fire_start: date
    pre_fire_end: date
    post_fire_start: date
    post_fire_end: date
    severity_classification: bool = Field(
        default=True,
        description="Also report threshold-based spectral severity classes; the "
        "continuous dNBR is always produced",
    )
    severity_scheme: str = Field(
        default="key-benson-2006",
        description="A scheme id from /api/v1/config/public, or 'custom' with custom_thresholds",
    )
    custom_thresholds: list[float] | None = Field(
        default=None,
        max_length=9,
        description="Ascending dNBR breakpoints (lower-inclusive) for severity_scheme='custom'",
    )


class AnalysisCreateRequest(BaseModel):
    """Submit a new analysis.

    Exactly one of ``region_id`` / ``bbox`` / ``geometry`` must be provided.
    ``bbox`` is ``[min_lon, min_lat, max_lon, max_lat]`` in WGS84. ``geometry``
    is a GeoJSON Polygon geometry object (not a Feature) in WGS84, restricted
    to a single exterior ring — no holes — of at most 256 vertices.
    """

    model_config = ConfigDict(extra="forbid")

    region_id: uuid.UUID | None = None
    operation: str = Field(
        default="ndvi",
        description="Spectral-index operation to run; the available operations "
        "are advertised by /api/v1/config/public.",
    )
    bbox: tuple[float, float, float, float] | None = None
    geometry: dict[str, Any] | None = None
    start_date: date | None = Field(
        default=None,
        description="Required for workflow=timeseries. For wildfire_dnbr it may be "
        "omitted; the stored range is then pre_fire_start..post_fire_end.",
    )
    end_date: date | None = None
    workflow: Literal["timeseries", "wildfire_dnbr"] = Field(
        default="timeseries",
        description="timeseries = index time series over [start_date, end_date]; "
        "wildfire_dnbr = pre/post-fire dNBR from the windows in `wildfire` "
        "(operation must be nbr, and defaults to it)",
    )
    land_cover: bool = Field(
        default=True,
        description="Stratify statistics by ESA WorldCover land-cover class",
    )
    temporal_context: TemporalContextRequest | None = Field(
        default=None,
        description="Seasonal baseline, anomalies, trend, and phenology (timeseries workflow only)",
    )
    wildfire: WildfireRequest | None = None
    max_cloud_cover_pct: float = Field(default=20.0, ge=0.0, le=100.0)
    scene_limit: int | None = Field(default=None, ge=1)
    selection_strategy: Literal["temporal", "seasonal"] = Field(
        default="temporal",
        description="How observations are chosen. 'temporal' spreads scenes evenly "
        "across the range (best within one growing season). 'seasonal' takes one "
        "scene per year from the same part of the calendar — use this for "
        "multi-year comparisons, because the seasonal NDVI swing is far larger "
        "than any year-to-year trend.",
    )
    seasonal_target_month: int | None = Field(
        default=None,
        ge=1,
        le=12,
        description="Calendar month the seasonal strategy anchors on. Defaults to "
        "the midpoint month of the requested range.",
    )


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class FireEventResponse(BaseModel):
    """Documented fire context for a curated wildfire region.

    Dates PROPOSE analysis windows; every result still comes from the
    Sentinel-2 observations actually selected.
    """

    kind: Literal["wildfire"] = "wildfire"
    name: str
    start_date: date
    end_date: date | None = None
    end_date_note: str | None = None
    suggested_pre_fire: dict[str, date]
    suggested_post_fire: dict[str, date]
    source_note: str


class RegionResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    group: str = Field(default="Global", description="UI grouping, e.g. Michigan or Global")
    description: str
    bbox: list[float]
    geometry: dict[str, Any]
    area_km2: float
    is_predefined: bool
    event: FireEventResponse | None = None


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
    land_cover: str | None = None
    temporal_context: str | None = None
    wildfire: str | None = None


class TemporalOptionsResponse(BaseModel):
    enabled: bool
    baseline_years: int


class WildfireOptionsResponse(BaseModel):
    pre_fire_start: date
    pre_fire_end: date
    post_fire_start: date
    post_fire_end: date
    severity_classification: bool
    severity_scheme: str
    custom_thresholds: list[float] | None = None


class AnalysisOptionsResponse(BaseModel):
    land_cover: bool
    land_cover_dataset: str | None = None
    temporal: TemporalOptionsResponse
    wildfire: WildfireOptionsResponse | None = None


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
    selection_strategy: str = "temporal"
    seasonal_target_month: int | None = None
    workflow: str = "timeseries"
    options: AnalysisOptionsResponse
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
    role: str | None = Field(
        default=None, description="pre_fire / post_fire in the wildfire workflow"
    )
    source_provider: str
    assets: dict[str, Any] = Field(
        description="Original unsigned STAC asset hrefs, keyed by item id then role"
    )
    quality: dict[str, Any] | None
    bbox: list[float] | None


class QualityResponse(BaseModel):
    """Structured quality metadata (earth_observation.quality.QualityInfo)."""

    state: str
    reasons: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class AnomalySummary(BaseModel):
    """Entire-AOI seasonal anomaly of one observation (statistical inference)."""

    result_kind: Literal["statistical_inference"] = "statistical_inference"
    expected: float | None
    absolute_anomaly: float | None
    relative_anomaly_pct: float | None
    robust_z: float | None
    classification: str
    baseline_n_samples: int
    baseline_n_years: int
    iqr_low: float | None
    iqr_high: float | None
    range_low: float | None
    range_high: float | None
    quality_state: str


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
    role: str | None = None
    anomaly: AnomalySummary | None = Field(
        default=None,
        description="Entire-AOI seasonal anomaly when temporal context was computed",
    )


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


# --- land cover ----------------------------------------------------------------


class LandCoverClassLegend(BaseModel):
    code: int
    key: str
    name: str
    color: str
    users_accuracy_pct: float | None = None
    users_accuracy_ci_pct: float | None = None
    producers_accuracy_pct: float | None = None
    producers_accuracy_ci_pct: float | None = None


class LandCoverDatasetResponse(BaseModel):
    id: str
    title: str
    collection: str
    product_version: str
    reference_year: int
    resolution_m: float
    provider: str
    license: str
    license_url: str
    attribution: str
    citation: str
    doi: str
    documentation_url: str
    validation_report_url: str
    overall_accuracy_pct: float | None
    overall_accuracy_ci_pct: float | None
    accuracy_source: str
    notes: list[str] = Field(default_factory=list)
    legend: list[LandCoverClassLegend] = Field(default_factory=list)


class CompositionEntryResponse(BaseModel):
    class_code: int
    class_key: str
    class_name: str
    color: str
    pixel_count: int
    area_km2: float
    aoi_pct: float
    users_accuracy_pct: float | None = None
    producers_accuracy_pct: float | None = None


class ClassStatsResponse(BaseModel):
    """Index statistics of one land-cover class in one observation (a measurement)."""

    class_code: int
    class_key: str
    class_name: str
    aoi_pixel_count: int
    aoi_area_km2: float
    aoi_pct: float
    valid_pixel_count: int
    valid_fraction: float
    mean: float | None
    median: float | None
    std: float | None
    min: float | None
    max: float | None
    p10: float | None
    p25: float | None
    p75: float | None
    p90: float | None
    quality: QualityResponse


class LandCoverObservation(BaseModel):
    scene_id: uuid.UUID
    stac_item_id: str
    observed_at: datetime
    role: str | None = None
    classes: list[ClassStatsResponse]


class LandCoverResponse(BaseModel):
    analysis_id: uuid.UUID
    status: Literal["not_requested", "pending", "computed", "unavailable"]
    result_kind: Literal["measurement"] = "measurement"
    operation: str
    detail: str | None = Field(
        default=None, description="Why stratification is unavailable, when it is"
    )
    dataset: LandCoverDatasetResponse | None = None
    selection_reason: str | None = None
    reference_year_quality: QualityResponse | None = None
    thresholds: dict[str, Any] = Field(default_factory=dict)
    aoi_pixel_count: int | None = None
    unlabeled_pct: float | None = None
    composition: list[CompositionEntryResponse] = Field(default_factory=list)
    observations: list[LandCoverObservation] = Field(default_factory=list)
    note: str = ""


# --- temporal context / wildfire -------------------------------------------------


class TemporalContextResponse(BaseModel):
    """Temporal-context document (earth_observation.temporal.TemporalContextDocument).

    ``document`` is the worker's checksummed ``temporal_context.json``
    verbatim (validated by the worker against the science package's model);
    ``status`` is always present so a client can render every state.
    """

    analysis_id: uuid.UUID
    status: Literal["not_requested", "pending", "computed", "skipped", "unavailable"]
    detail: str | None = None
    document: dict[str, Any] | None = None


class WildfireResponse(BaseModel):
    """Wildfire dNBR document (earth_observation.wildfire.WildfireDocument)."""

    analysis_id: uuid.UUID
    status: Literal["not_applicable", "pending", "computed", "unavailable"]
    detail: str | None = None
    document: dict[str, Any] | None = None


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


class PublicOperationInfo(BaseModel):
    """One spectral-index operation the deployment can run."""

    id: str = Field(description="Operation name to send as `operation` on submission")
    title: str
    description: str = Field(description="Plain-language note on what the index shows")
    display_min: float
    display_max: float
    change_display_range: float = Field(
        description="Half-range of the change-map colormap (delta spans -range..+range)"
    )
    legend: dict[str, Any] = Field(
        description="Preview-legend spec (stops, labels, wording) matching the "
        "operation's preview colormap"
    )


class SeverityClassInfo(BaseModel):
    code: int
    key: str
    label: str
    lower: float | None
    upper: float | None
    color: str


class SeveritySchemeInfo(BaseModel):
    id: str
    title: str
    citation: str
    note: str
    boundary_rule: str
    calibrated_for_sensor: bool
    classes: list[SeverityClassInfo]


class LandCoverConfigInfo(BaseModel):
    enabled: bool
    default_dataset: str
    datasets: list[LandCoverDatasetResponse]
    min_class_pixels: int
    min_class_valid_fraction: float


class TemporalConfigInfo(BaseModel):
    enabled: bool
    default_baseline_years: int
    max_baseline_years: int
    baseline_window_days: int
    max_baseline_acquisitions: int
    anomaly_z_threshold: float
    min_valid_fraction: float


class WildfireConfigInfo(BaseModel):
    enabled: bool
    default_severity_scheme: str
    severity_schemes: list[SeveritySchemeInfo]
    dnbr_legend: dict[str, Any] = Field(
        description="Continuous dNBR preview legend (stops, labels, sign convention)"
    )
    max_window_days: int
    seasonal_tolerance_days: int
    min_paired_valid_pct: float
    formula: str
    sign_convention: str


class PublicConfigResponse(BaseModel):
    environment: str
    demo_mode: bool
    submissions_enabled: bool
    max_aoi_area_km2: float
    min_aoi_area_km2: float
    custom_areas_enabled: bool = Field(
        default=True, description="Whether visitor-drawn areas of interest are accepted"
    )
    max_custom_aoi_area_km2: float = Field(
        default=2.0, description="Maximum area for a visitor-drawn AOI, in km²"
    )
    max_custom_aoi_vertices: int = Field(
        default=256,
        description="Vertex ceiling for a drawn polygon's exterior ring, "
        "excluding the closing vertex",
    )
    max_date_span_days: int
    min_start_date: date
    max_scene_limit: int
    default_scene_limit: int
    selection_strategies: list[str] = Field(
        default_factory=lambda: ["temporal", "seasonal"],
        description="Available observation-selection strategies",
    )
    seasonal_recommended_above_days: int = Field(
        default=400,
        description="Spans longer than this should use the seasonal strategy; an "
        "evenly-spread series over multiple years mostly measures season, not trend",
    )
    max_cloud_cover_pct: float
    default_cloud_cover_pct: float
    map_default_center: tuple[float, float]
    map_default_zoom: float
    ndvi_legend: dict[str, Any]
    operations: list[PublicOperationInfo] = Field(
        description="Spectral-index operations this deployment can run",
    )
    demo_analysis_id: uuid.UUID | None
    wildfire_demo_analysis_id: uuid.UUID | None = None
    workflows: list[str] = Field(default_factory=lambda: ["timeseries", "wildfire_dnbr"])
    land_cover: LandCoverConfigInfo | None = None
    temporal_context: TemporalConfigInfo | None = None
    wildfire: WildfireConfigInfo | None = None
    processing_version: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, str] = Field(default_factory=dict)
