"""Shared datatypes for scene discovery, processing configuration, and results.

Everything here is JSON-serializable so configuration snapshots and results
can be persisted verbatim into provenance documents and the database.
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from earth_observation.quality import QualityInfo


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
    """STAC asset keys for the band roles index processing may require.

    ``red`` / ``nir`` / ``swir`` are the spectral roles referenced by
    :mod:`earth_observation.indices`; ``green`` / ``blue`` are reserved for
    future indices (NDWI, EVI) so adding them later is config-only. ``scl`` is
    always required separately for masking — it is not part of any index's
    required roles.
    """

    model_config = ConfigDict(frozen=True)

    red: str = "B04"
    nir: str = "B08"
    swir: str = "B12"
    green: str = "B03"
    blue: str = "B02"
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


class LandCoverConfig(BaseModel):
    """Thresholds governing land-cover-stratified statistics.

    See docs/land-cover-stratification.md. A class that fails a threshold is
    still reported (pixel counts, area, share) but its index statistics are
    ``None`` with a structured quality state — never zero.
    """

    model_config = ConfigDict(frozen=True)

    min_class_pixels: int = Field(
        default=100,
        description="Classes with fewer AOI pixels than this (100 px = 1 ha at 10 m) "
        "get no index statistics (insufficient_samples)",
    )
    min_class_valid_fraction: float = Field(
        default=0.5,
        description="Minimum fraction of a class's AOI pixels that must carry a valid "
        "index value in an observation; below it the class statistics for that "
        "observation are withheld (insufficient_coverage), because clouds are "
        "spatially clustered and a small valid remnant is not representative",
    )
    max_reference_year_offset: int = Field(
        default=3,
        description="Observations more than this many years from the land-cover "
        "map's reference year are flagged reference_year_mismatch",
    )


class TemporalConfig(BaseModel):
    """Parameters of the temporal-context methods (docs/temporal-context.md)."""

    model_config = ConfigDict(frozen=True)

    baseline_window_days: int = Field(
        default=30,
        description="Historical observations within this many days of the target "
        "day-of-year (circular, leap-year aware) are seasonally comparable",
    )
    baseline_min_years: int = Field(
        default=3, description="Distinct reference years required for a baseline"
    )
    baseline_min_samples: int = Field(
        default=4, description="Comparable historical observations required for a baseline"
    )
    standardized_min_years: int = Field(
        default=5,
        description="Distinct reference years required before a robust standardized "
        "anomaly (and an unusual/typical classification) is reported",
    )
    anomaly_z_threshold: float = Field(
        default=2.0,
        description="|robust z| at or above which an observation is classified as "
        "unusually low/high relative to its seasonal baseline",
    )
    min_robust_sigma: float = Field(
        default=0.01,
        description="Floor on 1.4826 x MAD (index units); below it the spread is too "
        "small for a standardized anomaly to be meaningful",
    )
    relative_anomaly_min_abs_expected: float = Field(
        default=0.2,
        description="Relative (percent) anomalies are reported only when "
        "|expected| is at least this large; near zero they explode",
    )
    min_valid_fraction: float = Field(
        default=0.7,
        description="Observations whose stratum valid fraction is below this are "
        "excluded from baselines/trends and not assessed as targets "
        "(cloud_contaminated): a spatial mean over a cloud-riddled remnant is "
        "biased toward whatever the clouds did not cover",
    )
    max_baseline_acquisitions: int = Field(
        default=36,
        description="Deterministic cap on historical acquisitions measured for the "
        "baseline (cost control)",
    )
    trend_min_years: int = Field(
        default=5, description="Distinct years required before a trend is estimated"
    )
    trend_min_season_years: int = Field(
        default=10,
        description="Season-year values (one per calendar month per year) required "
        "for the seasonal Kendall test",
    )
    trend_alpha: float = Field(default=0.05, description="Two-sided significance level")
    phenology_min_observations: int = Field(
        default=8, description="Observations in a year required for phenology metrics"
    )
    phenology_min_months: int = Field(
        default=6, description="Distinct calendar months in a year required for phenology"
    )
    phenology_max_gap_days: int = Field(
        default=60,
        description="Largest gap between consecutive observations in a year for "
        "phenology metrics to be reported",
    )


class WildfireConfig(BaseModel):
    """Parameters of the wildfire dNBR workflow (docs/wildfire-dnbr.md)."""

    model_config = ConfigDict(frozen=True)

    max_snow_ice_pct: float = Field(
        default=10.0,
        description="Candidates whose granule snow/ice share (s2:snow_ice_percentage, "
        "AOI-overlap weighted) exceeds this are excluded: snow cover change is a "
        "major dNBR confounder",
    )
    seasonal_tolerance_days: int = Field(
        default=90,
        description="Pairs whose pre/post day-of-year distance exceeds this are "
        "flagged seasonal_mismatch (and ranked after every in-tolerance pair)",
    )
    cloud_bucket_pct: float = Field(
        default=5.0,
        description="Cloud cover is compared in buckets of this width when ranking "
        "pairs, so negligible cloud differences do not override seasonal matching",
    )
    min_paired_valid_pct: float = Field(
        default=50.0,
        description="Minimum share of the AOI valid on BOTH dates for a pair to be "
        "accepted; otherwise the next-ranked pair is tried",
    )
    good_paired_valid_pct: float = Field(
        default=80.0,
        description="Below this paired-valid share an accepted pair is flagged "
        "partial_paired_coverage",
    )
    max_scenes_processed: int = Field(
        default=6,
        description="Upper bound on acquisitions processed while searching for an "
        "acceptable pair (cost control)",
    )
    ranked_pairs_recorded: int = Field(
        default=10, description="How many top-ranked pairs are recorded in provenance"
    )
    display_min: float = Field(default=-0.5, description="dNBR preview lower bound")
    display_max: float = Field(default=1.0, description="dNBR preview upper bound")


class ProcessingConfig(BaseModel):
    """Snapshot of every parameter that affects scientific output.

    Stored verbatim on each analysis and embedded in provenance documents.
    """

    model_config = ConfigDict(frozen=True)

    collection: str = "sentinel-2-l2a"
    stac_endpoint: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    asset_keys: AssetKeys = AssetKeys()
    masked_scl_classes: tuple[int, ...] = DEFAULT_MASKED_SCL_CLASSES
    grid_resolution_m: float = Field(
        default=10.0,
        description="Canonical grid resolution; 10 m is the native GSD of the "
        "Sentinel-2 red and NIR bands",
    )
    min_valid_pixel_pct: float = Field(
        default=10.0,
        description="Acquisitions with fewer valid pixels than this (percent of AOI) "
        "are recorded but excluded from the time series",
    )
    min_aoi_coverage_pct: float = Field(
        default=99.0,
        description="Minimum percent of the AOI that the mosaicked granules of an "
        "acquisition must geometrically cover. Acquisitions below this are marked "
        "unusable so that every observation measures the same ground.",
    )
    min_aoi_overlap_pct: float = Field(
        default=1.0,
        description="Minimum AOI overlap for an individual granule to be worth "
        "reading. Coverage adequacy is decided per ACQUISITION via "
        "min_aoi_coverage_pct after mosaicking, not per granule.",
    )
    search_window_days: int = Field(
        default=370,
        description="Long date ranges are searched in consecutive windows of at "
        "most this many days. A single STAC query is capped at max_items and "
        "returns catalog order, so querying multi-year ranges in one call "
        "silently covers only the most recent part of the range.",
    )
    max_items_per_window: int = Field(
        default=150,
        description="STAC item cap applied PER search window, so total candidates "
        "scale with the requested span instead of starving early periods",
    )
    seasonal_tolerance_days: int = Field(
        default=30,
        description="For the seasonal strategy, how far an acquisition may fall "
        "from the target day-of-year and still represent that year",
    )
    ndvi_display_min: float = Field(default=-0.2, description="Preview colormap lower bound")
    ndvi_display_max: float = Field(default=0.9, description="Preview colormap upper bound")
    change_delta_threshold: float = Field(
        default=0.1,
        description="NDVI delta magnitude above which a pixel counts as increased "
        "or decreased in the change-map statistics; smaller changes are treated "
        "as within noise. Superseded at run time by the index registry "
        "(earth_observation.indices); retained for stored-config compatibility",
    )
    change_display_range: float = Field(
        default=0.4,
        description="Change preview colormap half-range; the diverging ramp spans "
        "-range..+range centered at zero. Superseded at run time by the index "
        "registry (earth_observation.indices); retained for stored-config "
        "compatibility",
    )
    preview_max_dim: int = Field(default=1024, description="Longest preview edge in pixels")
    output_nodata: float = -9999.0
    resampling: str = Field(
        default="nearest",
        description="Resampling used to align SCL (20 m) to the 10 m band grid; "
        "nearest preserves class labels",
    )
    processing_version: str = "1.0.0"
    land_cover: LandCoverConfig = LandCoverConfig()
    temporal: TemporalConfig = TemporalConfig()
    wildfire: WildfireConfig = WildfireConfig()


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
    snow_ice_pct: float | None = Field(
        default=None, description="Granule snow/ice share (s2:snow_ice_percentage)"
    )


class SceneSelection(BaseModel):
    """Outcome of deterministic scene selection."""

    selected: list[SceneCandidate]
    excluded: list[ExcludedScene]
    algorithm: str
    algorithm_version: str


class ExcludedScene(BaseModel):
    candidate: SceneCandidate
    reason: str


class CoverageStats(BaseModel):
    """Why every AOI pixel is or is not contributing to an observation.

    The categories are mutually exclusive and sum to ``aoi_pixel_count``, which
    is fixed by the canonical grid and identical for every observation in an
    analysis. This is what separates "the satellite did not see this ground"
    from "cloud" from "bad reflectance".
    """

    aoi_pixel_count: int = Field(description="Pixels inside the AOI on the canonical grid")
    covered_pixel_count: int = Field(
        description="AOI pixels reached by at least one contributing granule"
    )
    uncovered_pixel_count: int = Field(
        description="AOI pixels no granule covered (outside all source footprints)"
    )
    nodata_pixel_count: int = Field(
        description="Covered AOI pixels where the source carried nodata"
    )
    cloud_masked_pixel_count: int = Field(
        description="Cloud, cloud-shadow, and cirrus classes from the SCL policy"
    )
    snow_masked_pixel_count: int = Field(description="Snow/ice class from the SCL policy")
    other_masked_pixel_count: int = Field(
        description="Remaining masked SCL classes (saturated/defective)"
    )
    invalid_spectral_pixel_count: int = Field(
        description="Zero NDVI denominator; non-finite reflectance counts as nodata"
    )
    aoi_coverage_pct: float = Field(description="Geometric AOI coverage by source granules")
    valid_coverage_pct: float = Field(description="Percent of the AOI with usable NDVI")
    masked_pct: float = Field(description="Percent of the AOI removed by masking")
    missing_data_pct: float = Field(
        description="Percent of the AOI with no source data (uncovered + nodata)"
    )
    granule_count: int
    contributing_item_ids: list[str]
    tile_ids: list[str]


class SceneStats(BaseModel):
    """Per-observation NDVI statistics computed over valid (unmasked) pixels only."""

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


class ChangeStats(BaseModel):
    """Per-pixel NDVI change statistics over pixels valid in BOTH observations.

    ``valid_both_pct`` is the share of AOI pixels that are comparable at all;
    ``pct_increased`` / ``pct_decreased`` are shares of the valid-in-both
    pixels whose delta magnitude exceeds the configured threshold.
    """

    aoi_pixel_count: int
    valid_both_pixel_count: int
    valid_both_pct: float
    delta_mean: float | None
    delta_median: float | None
    delta_std: float | None
    delta_p10: float | None
    delta_p90: float | None
    pct_increased: float | None
    pct_decreased: float | None


class ClassStats(BaseModel):
    """Index statistics for one land-cover class within the AOI (one observation).

    ``aoi_*`` describe the class on the land-cover map (identical for every
    observation); ``valid_*`` and the statistics describe this observation.
    Statistics are ``None`` whenever ``quality`` is not valid.
    """

    class_code: int
    class_key: str
    class_name: str
    aoi_pixel_count: int = Field(description="AOI pixels mapped to this class")
    aoi_area_km2: float = Field(description="aoi_pixel_count x nominal pixel area")
    aoi_pct: float = Field(description="Share of ALL AOI pixels mapped to this class")
    valid_pixel_count: int = Field(description="Class pixels with a valid index value")
    valid_fraction: float = Field(description="valid_pixel_count / aoi_pixel_count, 0..1")
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    min: float | None = None
    max: float | None = None
    p10: float | None = None
    p25: float | None = None
    p75: float | None = None
    p90: float | None = None
    quality: QualityInfo = QualityInfo()


class RasterInfo(BaseModel):
    """Georeferencing of a produced raster, recorded for provenance."""

    crs: str
    transform: tuple[float, float, float, float, float, float]
    width: int
    height: int
    resolution: tuple[float, float]
    nodata: float


class SceneOutputs(BaseModel):
    """Local paths of files produced for one scene (pre-upload).

    The ``ndvi_*`` field names are historical: they hold the analysis's index
    outputs (``nbr.tif`` for an NBR analysis, etc.) and are generic containers.
    """

    ndvi_cog: str
    ndvi_preview: str
    true_color_preview: str | None
    scene_summary: str


class AcquisitionSummary(BaseModel):
    """Identity of one acquisition, independent of how many granules backed it."""

    key: str
    primary_item_id: str
    observed_at: datetime
    collection: str
    platform: str | None
    relative_orbit: str | None
    cloud_cover_pct: float | None
    contributing_item_ids: list[str]
    tile_ids: list[str]
    processing_baselines: list[str]
    snow_ice_pct: float | None = None
    assets: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="Original unsigned asset hrefs, keyed by item id then role",
    )


class SceneResult(BaseModel):
    """Full result of processing one acquisition onto the canonical grid."""

    acquisition: AcquisitionSummary
    usable: bool
    unusable_reason: str | None = None
    stats: SceneStats | None = None
    coverage: CoverageStats | None = None
    scaling: BandScaling | None = None
    raster: RasterInfo | None = None
    outputs: SceneOutputs | None = None
    class_stats: list[ClassStats] | None = Field(
        default=None,
        description="Per land-cover class statistics; None when no land-cover layer was supplied",
    )
    processing_seconds: float = 0.0
    warnings: list[str] = Field(default_factory=list)

    @property
    def observed_at(self) -> datetime:
        return self.acquisition.observed_at

    @property
    def item_id(self) -> str:
        return self.acquisition.primary_item_id


SceneSelection.model_rebuild()
