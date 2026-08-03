"""Domain model: regions, analyses, scenes, observations, artifacts.

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
    TRUE_COLOR_PREVIEW = "true_color_preview"
    SCENE_SUMMARY = "scene_summary"
    TIMESERIES_CSV = "timeseries_csv"
    ANALYSIS_SUMMARY = "analysis_summary"
    PROVENANCE = "provenance"


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
