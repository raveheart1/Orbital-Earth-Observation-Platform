"""Domain model: regions, analyses, scenes, observations, artifacts.

Land-cover class statistics and temporal anomalies are relational (one row per
observation x class / stratum) because they are queried — class time series,
"which observations were unusual". Naturally document-shaped results (the
temporal-context and wildfire documents, severity distributions) are
checksummed artifacts plus a compact block in ``analyses.summary``.

Enums are stored as constrained VARCHARs (``native_enum=False``) so adding a
member is an additive migration instead of a PostgreSQL ``ALTER TYPE``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from oeop_core.db.base import Base

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class AnalysisStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FailureCategory(str, enum.Enum):
    USER_INPUT = "user_input"
    DATA = "data"
    TRANSIENT = "transient"
    TIMEOUT = "timeout"
    INTERNAL = "internal"


class SceneSelectionStatus(str, enum.Enum):
    SELECTED = "selected"
    EXCLUDED = "excluded"


class ArtifactType(str, enum.Enum):
    NDVI_COG = "ndvi_cog"
    NDVI_PREVIEW = "ndvi_preview"
    NBR_COG = "nbr_cog"
    NBR_PREVIEW = "nbr_preview"
    TRUE_COLOR_PREVIEW = "true_color_preview"
    SCENE_SUMMARY = "scene_summary"
    TIMESERIES_CSV = "timeseries_csv"
    ANALYSIS_SUMMARY = "analysis_summary"
    NDVI_CHANGE_COG = "ndvi_change_cog"
    NDVI_CHANGE_PREVIEW = "ndvi_change_preview"
    NBR_CHANGE_COG = "nbr_change_cog"
    NBR_CHANGE_PREVIEW = "nbr_change_preview"
    FIRE_DETECTIONS = "fire_detections"
    LAND_COVER_COG = "land_cover_cog"
    LAND_COVER_PREVIEW = "land_cover_preview"
    LAND_COVER_SUMMARY = "land_cover_summary"
    TEMPORAL_CONTEXT = "temporal_context"
    DNBR_COG = "dnbr_cog"
    DNBR_PREVIEW = "dnbr_preview"
    BURN_SEVERITY_COG = "burn_severity_cog"
    BURN_SEVERITY_PREVIEW = "burn_severity_preview"
    WILDFIRE_SUMMARY = "wildfire_summary"
    PROVENANCE = "provenance"


class SceneRole(str, enum.Enum):
    """Role of an observation within a workflow (NULL for time-series scenes)."""

    PRE_FIRE = "pre_fire"
    POST_FIRE = "post_fire"


def _enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    geometry: Mapped[Any] = mapped_column(Geometry(geometry_type="POLYGON", srid=4326))
    bbox: Mapped[list[float]] = mapped_column(JSONVariant)
    area_km2: Mapped[float] = mapped_column(Float)
    is_predefined: Mapped[bool] = mapped_column(Boolean, default=True)
    region_group: Mapped[str] = mapped_column(
        String(40),
        default="Global",
        comment="Grouping shown in the UI, e.g. Michigan or Global",
    )
    event: Mapped[dict[str, Any] | None] = mapped_column(
        JSONVariant,
        nullable=True,
        comment="Documented event context (e.g. a wildfire's dates and suggested "
        "pre/post windows); proposes defaults, never supplies results",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    analyses: Mapped[list[Analysis]] = relationship(back_populates="region")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("regions.id", ondelete="SET NULL"), nullable=True
    )
    geometry: Mapped[Any | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=True
    )
    bbox: Mapped[list[float]] = mapped_column(JSONVariant)
    area_km2: Mapped[float] = mapped_column(Float)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    collection: Mapped[str] = mapped_column(String(80), default="sentinel-2-l2a")
    max_cloud_cover_pct: Mapped[float] = mapped_column(Float)
    scene_limit: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(40), default="ndvi")
    workflow: Mapped[str] = mapped_column(
        String(40),
        default="timeseries",
        index=True,
        comment="timeseries = index time series; wildfire_dnbr = pre/post-fire dNBR",
    )
    options: Mapped[dict[str, Any] | None] = mapped_column(
        JSONVariant,
        nullable=True,
        comment="Validated AnalysisOptions snapshot (land cover, temporal context, "
        "wildfire windows); NULL for analyses that predate options",
    )
    selection_strategy: Mapped[str] = mapped_column(
        String(20),
        default="temporal",
        comment="temporal = evenly spread; seasonal = one per year at the same season",
    )
    seasonal_target_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_config: Mapped[dict[str, Any]] = mapped_column(JSONVariant)
    grid: Mapped[dict[str, Any] | None] = mapped_column(
        JSONVariant,
        nullable=True,
        comment="Canonical analysis grid every observation is aligned to",
    )
    processing_version: Mapped[str] = mapped_column(String(40))
    git_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[AnalysisStatus] = mapped_column(
        _enum(AnalysisStatus, "analysis_status"), default=AnalysisStatus.QUEUED, index=True
    )
    status_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_category: Mapped[FailureCategory | None] = mapped_column(
        _enum(FailureCategory, "failure_category"), nullable=True
    )
    failure_detail: Mapped[str | None] = mapped_column(
        String(1000), nullable=True, comment="Sanitized; never raw exception dumps"
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    output_prefix: Mapped[str | None] = mapped_column(String(300), nullable=True)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    region: Mapped[Region | None] = relationship(back_populates="analyses")
    scenes: Mapped[list[Scene]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    observations: Mapped[list[Observation]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_analyses_status_submitted", "status", "submitted_at"),)


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    stac_collection: Mapped[str] = mapped_column(String(80))
    stac_item_id: Mapped[str] = mapped_column(
        String(120), comment="Primary/representative granule of the acquisition"
    )
    acquisition_key: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Deterministic key grouping granules of one acquisition",
    )
    contributing_item_ids: Mapped[list[str] | None] = mapped_column(
        JSONVariant, nullable=True, comment="Every STAC item mosaicked for this observation"
    )
    tile_ids: Mapped[list[str] | None] = mapped_column(
        JSONVariant, nullable=True, comment="Sentinel-2 MGRS tiles contributing"
    )
    granule_count: Mapped[int] = mapped_column(Integer, default=1)
    aoi_coverage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    valid_pixel_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), comment="Acquisition (sensing) time, not processing time"
    )
    geometry: Mapped[Any | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True
    )
    bbox: Mapped[list[float] | None] = mapped_column(JSONVariant, nullable=True)
    cloud_cover_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_provider: Mapped[str] = mapped_column(
        String(120), default="Microsoft Planetary Computer"
    )
    platform: Mapped[str | None] = mapped_column(String(40), nullable=True)
    instruments: Mapped[list[str] | None] = mapped_column(JSONVariant, nullable=True)
    assets: Mapped[dict[str, Any]] = mapped_column(
        JSONVariant,
        comment="Original unsigned asset hrefs, keyed by contributing item id then role",
    )
    selection_status: Mapped[SceneSelectionStatus] = mapped_column(
        _enum(SceneSelectionStatus, "scene_selection_status")
    )
    exclusion_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="pre_fire / post_fire in the wildfire workflow"
    )
    quality: Mapped[dict[str, Any] | None] = mapped_column(
        JSONVariant,
        nullable=True,
        comment="aoi_overlap_pct, processing_baseline, unusable_reason, warnings",
    )

    analysis: Mapped[Analysis] = relationship(back_populates="scenes")
    observation: Mapped[Observation | None] = relationship(back_populates="scene")

    __table_args__ = (
        UniqueConstraint("analysis_id", "stac_item_id", name="uq_scenes_analysis_item"),
        Index("ix_scenes_analysis_observed", "analysis_id", "observed_at"),
    )


class Observation(Base):
    """Per-scene NDVI measurement (the processing result for one usable scene)."""

    __tablename__ = "observations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), unique=True
    )
    ndvi_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_median: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_p10: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_p25: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_p75: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_p90: Mapped[float | None] = mapped_column(Float, nullable=True)
    valid_pixel_count: Mapped[int] = mapped_column(BigInteger)
    masked_pixel_count: Mapped[int] = mapped_column(BigInteger)
    aoi_pixel_count: Mapped[int] = mapped_column(BigInteger)
    valid_pixel_pct: Mapped[float] = mapped_column(Float)
    zero_denominator_pixel_count: Mapped[int] = mapped_column(BigInteger, default=0)
    uncovered_pixel_count: Mapped[int] = mapped_column(BigInteger, default=0)
    aoi_coverage_pct: Mapped[float] = mapped_column(Float, default=100.0)
    valid_coverage_pct: Mapped[float] = mapped_column(Float, default=0.0)
    missing_data_pct: Mapped[float] = mapped_column(Float, default=0.0)
    granule_count: Mapped[int] = mapped_column(Integer, default=1)
    mask_scl_classes: Mapped[list[int]] = mapped_column(JSONVariant)
    band_scaling: Mapped[dict[str, Any]] = mapped_column(JSONVariant)
    processing_params: Mapped[dict[str, Any]] = mapped_column(JSONVariant)
    processing_seconds: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    analysis: Mapped[Analysis] = relationship(back_populates="observations")
    scene: Mapped[Scene] = relationship(back_populates="observation")
    class_stats: Mapped[list[ObservationClassStats]] = relationship(
        back_populates="observation", cascade="all, delete-orphan"
    )
    anomalies: Mapped[list[ObservationAnomaly]] = relationship(
        back_populates="observation", cascade="all, delete-orphan"
    )


class ObservationClassStats(Base):
    """Index statistics of one land-cover class in one observation (a measurement)."""

    __tablename__ = "observation_class_stats"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("observations.id", ondelete="CASCADE"), index=True
    )
    class_code: Mapped[int] = mapped_column(Integer)
    class_key: Mapped[str] = mapped_column(String(40))
    class_name: Mapped[str] = mapped_column(String(80))
    aoi_pixel_count: Mapped[int] = mapped_column(BigInteger)
    aoi_area_km2: Mapped[float] = mapped_column(Float)
    aoi_pct: Mapped[float] = mapped_column(Float)
    valid_pixel_count: Mapped[int] = mapped_column(BigInteger)
    valid_fraction: Mapped[float] = mapped_column(Float)
    index_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    index_median: Mapped[float | None] = mapped_column(Float, nullable=True)
    index_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    index_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    index_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    index_p10: Mapped[float | None] = mapped_column(Float, nullable=True)
    index_p25: Mapped[float | None] = mapped_column(Float, nullable=True)
    index_p75: Mapped[float | None] = mapped_column(Float, nullable=True)
    index_p90: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_state: Mapped[str] = mapped_column(String(32))
    quality: Mapped[dict[str, Any]] = mapped_column(JSONVariant)

    observation: Mapped[Observation] = relationship(back_populates="class_stats")

    __table_args__ = (
        UniqueConstraint("observation_id", "class_code", name="uq_class_stats_observation_class"),
    )


class ObservationAnomaly(Base):
    """Seasonal anomaly of one observation for one stratum (a statistical inference).

    ``stratum`` is ``aoi`` or ``class:<code>``.
    """

    __tablename__ = "observation_anomalies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("observations.id", ondelete="CASCADE"), index=True
    )
    stratum: Mapped[str] = mapped_column(String(40))
    class_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected: Mapped[float | None] = mapped_column(Float, nullable=True)
    absolute_anomaly: Mapped[float | None] = mapped_column(Float, nullable=True)
    relative_anomaly_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    robust_z: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_n_samples: Mapped[int] = mapped_column(Integer)
    baseline_n_years: Mapped[int] = mapped_column(Integer)
    robust_sigma: Mapped[float | None] = mapped_column(Float, nullable=True)
    iqr_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    iqr_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification: Mapped[str] = mapped_column(String(32))
    quality_state: Mapped[str] = mapped_column(String(32))
    quality: Mapped[dict[str, Any]] = mapped_column(JSONVariant)

    observation: Mapped[Observation] = relationship(back_populates="anomalies")

    __table_args__ = (
        UniqueConstraint("observation_id", "stratum", name="uq_anomalies_observation_stratum"),
        Index("ix_anomalies_analysis_classification", "analysis_id", "classification"),
    )


class AcquisitionMeasurement(Base):
    """Deterministic cache of per-acquisition measurements (statistics only).

    Keyed by :func:`earth_observation.cache_keys.measurement_cache_key`, which
    covers every input of the measurement. Safe to truncate: a miss simply
    recomputes. Analyses never reference rows here — their temporal-context
    artifact records the measured values and the cache keys used.
    """

    __tablename__ = "acquisition_measurements"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    grid_signature: Mapped[str] = mapped_column(String(200), index=True)
    operation: Mapped[str] = mapped_column(String(40))
    acquisition_key: Mapped[str] = mapped_column(String(200))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processing_version: Mapped[str] = mapped_column(String(40))
    measurement: Mapped[dict[str, Any]] = mapped_column(JSONVariant)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=True
    )
    artifact_type: Mapped[ArtifactType] = mapped_column(_enum(ArtifactType, "artifact_type"))
    container: Mapped[str] = mapped_column(String(80))
    blob_path: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    crs: Mapped[str | None] = mapped_column(String(40), nullable=True)
    bbox: Mapped[list[float] | None] = mapped_column(JSONVariant, nullable=True)
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    analysis: Mapped[Analysis] = relationship(back_populates="artifacts")
    scene: Mapped[Scene | None] = relationship()

    __table_args__ = (
        UniqueConstraint("analysis_id", "blob_path", name="uq_artifacts_analysis_path"),
    )
