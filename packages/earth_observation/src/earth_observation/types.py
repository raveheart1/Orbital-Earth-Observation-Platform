"""Shared datatypes for scene discovery, processing configuration, and results.

Everything here is JSON-serializable so configuration snapshots and results
can be persisted verbatim into provenance documents and the database.
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SCLClass(IntEnum):
    """Sentinel-2 L2A Scene Classification Layer classes (processing baseline >= 04.00).

    Reference: Sentinel-2 Level-2A Algorithm Theoretical Basis Document.
    """

    NO_DATA = 0
    SATURATED_OR_DEFECTIVE = 1
    CAST_SHADOWS = 2
    CLOUD_SHADOWS = 3
    VEGETATION = 4
    NOT_VEGETATED = 5
    WATER = 6
    UNCLASSIFIED = 7
    CLOUD_MEDIUM_PROBABILITY = 8
    CLOUD_HIGH_PROBABILITY = 9
    THIN_CIRRUS = 10
    SNOW_OR_ICE = 11


#: Default mask policy. Each entry is deliberate — see docs/scientific-methodology.md.
#: - NO_DATA / SATURATED_OR_DEFECTIVE: sensor artifacts, never valid reflectance.
#: - CLOUD_SHADOWS: shadowed reflectance biases NDVI low.
#: - CLOUD_MEDIUM_PROBABILITY / CLOUD_HIGH_PROBABILITY: cloud contamination.
#: - THIN_CIRRUS: partial optical contamination that skews the red/NIR ratio.
#: - SNOW_OR_ICE: NDVI over snow is not a vegetation signal.
#: CAST_SHADOWS (terrain) and WATER are retained: they are real surface
#: observations; water simply produces legitimately negative NDVI.
DEFAULT_MASKED_SCL_CLASSES: tuple[int, ...] = (
    SCLClass.NO_DATA,
    SCLClass.SATURATED_OR_DEFECTIVE,
    SCLClass.CLOUD_SHADOWS,
    SCLClass.CLOUD_MEDIUM_PROBABILITY,
    SCLClass.CLOUD_HIGH_PROBABILITY,
    SCLClass.THIN_CIRRUS,
    SCLClass.SNOW_OR_ICE,
)


class AssetKeys(BaseModel):
    """STAC asset keys used for NDVI processing on a given collection."""

    model_config = ConfigDict(frozen=True)

    red: str = "B04"
    nir: str = "B08"
    scl: str = "SCL"
    visual: str = "visual"


class BandScaling(BaseModel):
    """Digital-number -> reflectance conversion: ``reflectance = dn * scale + offset``.

    NDVI is invariant to a common multiplicative scale but NOT to an additive
    offset, so the offset introduced by Sentinel-2 processing baseline 04.00
    (DN' = DN + 1000) must be removed before computing the index.
    """

    model_config = ConfigDict(frozen=True)

    scale: float = 1.0e-4
    offset: float = 0.0
    source: str = Field(
        default="default",
        description="Where the scaling came from: 'raster_ext', 'baseline_heuristic', or 'default'",
    )


class ProcessingConfig(BaseModel):
    """Snapshot of every parameter that affects scientific output.

    Stored verbatim on each analysis and embedded in provenance documents.
    """

    model_config = ConfigDict(frozen=True)

    collection: str = "sentinel-2-l2a"
    stac_endpoint: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    asset_keys: AssetKeys = AssetKeys()
    masked_scl_classes: tuple[int, ...] = DEFAULT_MASKED_SCL_CLASSES
    min_valid_pixel_pct: float = Field(
        default=10.0,
        description="Scenes with fewer valid pixels than this (percent of AOI) are "
        "recorded but excluded from the time series",
    )
    min_aoi_overlap_pct: float = Field(
        default=25.0,
        description="Minimum percent of the AOI a scene footprint must cover to be selected",
    )
    max_candidate_items: int = Field(
        default=200, description="Maximum STAC items fetched before selection"
    )
    ndvi_display_min: float = Field(default=-0.2, description="Preview colormap lower bound")
    ndvi_display_max: float = Field(default=0.9, description="Preview colormap upper bound")
    preview_max_dim: int = Field(default=1024, description="Longest preview edge in pixels")
    output_nodata: float = -9999.0
    resampling: str = Field(
        default="nearest",
        description="Resampling used to align SCL (20 m) to the 10 m band grid; "
        "nearest preserves class labels",
    )
    processing_version: str = "1.0.0"


class SceneCandidate(BaseModel):
    """A STAC item reduced to the fields the platform needs.

    ``assets`` holds ORIGINAL (unsigned) hrefs — signing happens immediately
    before access and signed URLs are never persisted.
    """

    item_id: str
    collection: str
    observed_at: datetime
    cloud_cover_pct: float | None
    geometry: dict[str, Any]
    bbox: tuple[float, float, float, float]
    epsg: int | None
    platform: str | None
    instruments: list[str] | None
    processing_baseline: str | None
    assets: dict[str, str]
    aoi_overlap_pct: float | None = None


class SceneSelection(BaseModel):
    """Outcome of deterministic scene selection."""

    selected: list[SceneCandidate]
    excluded: list[ExcludedScene]
    algorithm: str
    algorithm_version: str


class ExcludedScene(BaseModel):
    candidate: SceneCandidate
    reason: str


class SceneStats(BaseModel):
    """Per-scene NDVI statistics computed over valid (unmasked) pixels only."""

    valid_pixel_count: int
    masked_pixel_count: int
    aoi_pixel_count: int
    valid_pixel_pct: float
    zero_denominator_pixel_count: int
    ndvi_min: float | None
    ndvi_max: float | None
    ndvi_mean: float | None
    ndvi_median: float | None
    ndvi_std: float | None
    ndvi_p10: float | None
    ndvi_p25: float | None
    ndvi_p75: float | None
    ndvi_p90: float | None


class RasterInfo(BaseModel):
    """Georeferencing of a produced raster, recorded for provenance."""

    crs: str
    transform: tuple[float, float, float, float, float, float]
    width: int
    height: int
    resolution: tuple[float, float]
    nodata: float


class SceneOutputs(BaseModel):
    """Local paths of files produced for one scene (pre-upload)."""

    ndvi_cog: str
    ndvi_preview: str
    true_color_preview: str | None
    scene_summary: str


class SceneResult(BaseModel):
    """Full result of processing a single scene."""

    candidate: SceneCandidate
    usable: bool
    unusable_reason: str | None = None
    stats: SceneStats | None = None
    scaling: BandScaling | None = None
    raster: RasterInfo | None = None
    outputs: SceneOutputs | None = None
    processing_seconds: float = 0.0
    warnings: list[str] = Field(default_factory=list)


SceneSelection.model_rebuild()
