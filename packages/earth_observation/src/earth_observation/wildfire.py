"""Wildfire pre/post-fire change analysis: dNBR and optional severity classes.

    dNBR = NBR_pre - NBR_post

Sign convention (enforced by a regression test): healthy canopy is strongly
NIR-reflective and SWIR2-absorptive (high NBR); char, ash, and exposed soil
reverse that contrast, so burning LOWERS NBR and yields POSITIVE dNBR.
Negative dNBR means NBR increased between the dates (e.g. post-fire regrowth,
or a pre-fire scene that was itself disturbed or senescent). NOTE the generic
per-pixel change map of a time-series analysis uses the opposite order
(later - earlier); the wildfire workflow does not produce that map, so the
two conventions never appear side by side.

What dNBR is — and is not
-------------------------
dNBR measures the magnitude of a SPECTRAL change between two dates on the
canonical grid, for pixels valid on both dates. It is remote-sensing burn
severity at best: it is not field-observed ecological or soil burn severity
(e.g. Composite Burn Index plots), and the relationship between the two
depends on ecosystem, fire behaviour, timing, and post-fire conditions.
Threshold-based severity classes are an optional INTERPRETATION layered on
the continuous measurement, under a named, documented scheme whose
thresholds were not calibrated for this sensor or ecosystem; they are always
presented as "spectral severity class", never as a field outcome.

Pair selection (``fire-pair-seasonal-lowest-cloud`` v1.0.0)
-----------------------------------------------------------
1. Candidates are acquisitions inside the pre-fire or post-fire window.
2. Hard gates (recorded as exclusion reasons): AOI coverage below the
   threshold, cloud cover above the request threshold, granule snow/ice
   share above ``WildfireConfig.max_snow_ice_pct``.
3. Every (pre, post) pair of eligible candidates is ranked by the tuple
   ``(outside seasonal tolerance, cloud bucket of the cloudier scene,
   snow bucket of the snowier scene, seasonal offset in days, timing offset,
   pre key, post key)`` where the seasonal offset is the circular
   day-of-year distance between the two dates and the timing offset is the
   days from the pre scene to the END of the pre window plus the days from
   the START of the post window to the post scene (closest to the event).
4. Pairs are tried in rank order: each scene is processed once (memoised);
   a pair is accepted when both scenes are usable and the paired-valid share
   of the AOI reaches ``min_paired_valid_pct``. At most
   ``max_scenes_processed`` scenes are processed. Every attempt and its
   outcome is recorded — the first/last image is never used by default.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, Field

from earth_observation.acquisition import Acquisition
from earth_observation.quality import QualityInfo, ResultKind
from earth_observation.types import ClassStats, WildfireConfig

WILDFIRE_SCHEMA_VERSION = "1.0.0"

DNBR_FORMULA = "dNBR = NBR_pre - NBR_post"
DNBR_SIGN_CONVENTION = (
    "Positive dNBR means NBR decreased from the pre-fire to the post-fire "
    "observation (loss of NIR reflectance and/or gain in SWIR2 reflectance), the "
    "spectral direction associated with burning; negative dNBR means NBR "
    "increased (e.g. regrowth)."
)
DNBR_MASK_POLICY = "valid_in_both"

PAIR_SELECTION_ALGORITHM = "fire-pair-seasonal-lowest-cloud"
PAIR_SELECTION_VERSION = "1.0.0"

#: Candidate exclusion reasons.
REASON_COVERAGE = "insufficient_aoi_coverage"
REASON_CLOUD = "cloud_cover_above_threshold"
REASON_SNOW = "snow_ice_above_threshold"
REASON_OUTSIDE_WINDOWS = "outside_pre_and_post_windows"
REASON_NOT_SELECTED = "not_selected_lower_ranked"
REASON_NOT_PROCESSED = "not_processed_scene_budget"

#: Pair-attempt rejection reasons.
ATTEMPT_PRE_UNUSABLE = "pre_fire_scene_unusable"
ATTEMPT_POST_UNUSABLE = "post_fire_scene_unusable"
ATTEMPT_PAIRED_VALID_LOW = "paired_valid_below_threshold"

#: Code for "no severity class" on the class raster.
SEVERITY_NODATA = 0

#: Nominal dNBR range of Key & Benson (2006); values beyond it are counted as
#: a quality flag (often residual cloud, water, or misregistration).
NOMINAL_DNBR_MIN = -0.5
NOMINAL_DNBR_MAX = 1.3


@dataclass(frozen=True)
class SeverityClass:
    """One spectral severity class: ``lower <= dNBR < upper``.

    ``lower=None`` is -infinity, ``upper=None`` is +infinity. ``code`` is the
    value written to the class raster (1-based; 0 = no data).
    """

    code: int
    key: str
    label: str
    lower: float | None
    upper: float | None
    color: str

    def rgb(self) -> tuple[int, int, int]:
        value = self.color.lstrip("#")
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


@dataclass(frozen=True)
class SeverityScheme:
    id: str
    title: str
    classes: tuple[SeverityClass, ...]
    citation: str
    note: str
    boundary_rule: str = "lower-inclusive, upper-exclusive (lower <= dNBR < upper)"
    calibrated_for_sensor: bool = False

    def to_metadata(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "citation": self.citation,
            "note": self.note,
            "boundary_rule": self.boundary_rule,
            "calibrated_for_sensor": self.calibrated_for_sensor,
            "classes": [
                {
                    "code": c.code,
                    "key": c.key,
                    "label": c.label,
                    "lower": c.lower,
                    "upper": c.upper,
                    "color": c.color,
                }
                for c in self.classes
            ],
        }


#: Key & Benson (2006), FIREMON Landscape Assessment, example dNBR ranges
#: (published x1000): enhanced regrowth high -500..-251, enhanced regrowth
#: low -250..-101, unburned -100..+99, low +100..+269, moderate-low
#: +270..+439, moderate-high +440..+659, high +660..+1300. Converted to NBR
#: units with lower-inclusive bounds so integer-scaled values land exactly
#: where the published table puts them (e.g. -100 -> unburned, +100 -> low).
KEY_BENSON_2006 = SeverityScheme(
    id="key-benson-2006",
    title="Key & Benson (2006) dNBR ranges (spectral severity classes)",
    classes=(
        SeverityClass(
            1, "enhanced_regrowth_high", "Enhanced regrowth, high", None, -0.25, "#1b7837"
        ),
        SeverityClass(
            2, "enhanced_regrowth_low", "Enhanced regrowth, low", -0.25, -0.10, "#7fbf7b"
        ),
        SeverityClass(3, "unburned", "Unburned or unchanged", -0.10, 0.10, "#e7e7e7"),
        SeverityClass(4, "low", "Low", 0.10, 0.27, "#fee391"),
        SeverityClass(5, "moderate_low", "Moderate-low", 0.27, 0.44, "#fec44f"),
        SeverityClass(6, "moderate_high", "Moderate-high", 0.44, 0.66, "#ec7014"),
        SeverityClass(7, "high", "High", 0.66, None, "#8c2d04"),
    ),
    citation=(
        "Key, C. H., & Benson, N. C. (2006). Landscape Assessment (LA): Sampling "
        "and analysis methods. In FIREMON: Fire Effects Monitoring and Inventory "
        "System, USDA Forest Service Gen. Tech. Rep. RMRS-GTR-164-CD, LA-1-55."
    ),
    note=(
        "Example ranges published for Landsat TM/ETM+ dNBR; they are community "
        "guidance, not physical constants, and were not calibrated against field "
        "burn-severity plots for Sentinel-2 or for this ecosystem. Classes describe "
        "the magnitude of spectral change only."
    ),
)

SEVERITY_SCHEMES: dict[str, SeverityScheme] = {KEY_BENSON_2006.id: KEY_BENSON_2006}
DEFAULT_SEVERITY_SCHEME = KEY_BENSON_2006.id
CUSTOM_SCHEME_ID = "custom"


def custom_scheme(breakpoints: list[float]) -> SeverityScheme:
    """A user-configured scheme from ascending dNBR breakpoints.

    ``k`` breakpoints (1 <= k <= 9, strictly increasing, finite, within
    [-2, 2]) define ``k + 1`` classes ``class_1`` ... labelled by their
    bounds. Raises :class:`UserInputError` on invalid input.
    """
    raise NotImplementedError


def resolve_scheme(scheme_id: str, custom_thresholds: list[float] | None) -> SeverityScheme:
    """Registered scheme by id, or :func:`custom_scheme` for ``"custom"``.

    ``UserInputError`` for unknown ids, or thresholds given for a non-custom
    scheme / missing for ``"custom"``.
    """
    raise NotImplementedError


# --- measurement -----------------------------------------------------------------


class NbrObservationStats(BaseModel):
    acquisition_key: str
    primary_item_id: str
    observed_at: datetime
    valid_pixel_count: int
    valid_pct: float
    mean: float | None
    median: float | None


class DnbrStats(BaseModel):
    """Continuous dNBR statistics over the paired-valid AOI pixels."""

    result_kind: ResultKind = ResultKind.MEASUREMENT
    aoi_pixel_count: int
    pre_valid_pixel_count: int
    post_valid_pixel_count: int
    paired_valid_pixel_count: int
    paired_valid_pct: float = Field(description="Percent of AOI pixels valid on both dates")
    pixel_area_m2: float
    aoi_area_km2: float = Field(description="AOI pixel count x pixel area")
    paired_valid_area_km2: float
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    min: float | None = None
    max: float | None = None
    p05: float | None = None
    p10: float | None = None
    p25: float | None = None
    p75: float | None = None
    p90: float | None = None
    p95: float | None = None
    outside_nominal_range_pixel_count: int = Field(
        default=0,
        description="Paired-valid pixels with dNBR < -0.5 or > 1.3 (Key & Benson nominal range)",
    )
    quality: QualityInfo


def compute_dnbr(
    pre_nbr: npt.NDArray[np.floating],
    post_nbr: npt.NDArray[np.floating],
    aoi_mask: npt.NDArray[np.bool_],
    *,
    pixel_area_m2: float,
    config: WildfireConfig,
) -> tuple[npt.NDArray[np.float32], DnbrStats]:
    """dNBR = pre - post for pixels inside the AOI and finite on BOTH dates.

    Returns the float32 dNBR array (NaN elsewhere) and its statistics. Shape
    mismatches raise ``ValueError`` (both inputs must be on the canonical
    grid). Quality: paired-valid share below ``min_paired_valid_pct`` →
    ``insufficient_coverage`` (statistics still reported for transparency);
    below ``good_paired_valid_pct`` → flag ``partial_paired_coverage``;
    pixels beyond the nominal range → flag ``values_outside_nominal_range``.
    """
    raise NotImplementedError


class SeverityClassStats(BaseModel):
    code: int
    key: str
    label: str
    lower: float | None
    upper: float | None
    color: str
    pixel_count: int
    area_km2: float
    pct_of_paired_valid: float


def classify_severity(
    dnbr: npt.NDArray[np.floating],
    scheme: SeverityScheme,
    *,
    pixel_area_m2: float,
) -> tuple[npt.NDArray[np.uint8], list[SeverityClassStats]]:
    """Map continuous dNBR onto the scheme's classes (lower-inclusive bounds).

    Returns the uint8 class raster (``SEVERITY_NODATA`` where dNBR is NaN)
    and one entry per scheme class (zero-count classes included, so the
    distribution always sums to 100 % of the paired-valid area).
    """
    raise NotImplementedError


class ClassDnbr(BaseModel):
    """dNBR within one land-cover class (map reference year recorded separately)."""

    class_code: int
    class_key: str
    class_name: str
    color: str
    dnbr: ClassStats
    severity_distribution: list[SeverityClassStats] | None = None


def dnbr_by_land_cover(
    dnbr: npt.NDArray[np.floating],
    layer: Any,
    aoi_mask: npt.NDArray[np.bool_],
    *,
    land_cover_config: Any,
    pixel_area_m2: float,
    scheme: SeverityScheme | None,
) -> list[ClassDnbr]:
    """dNBR statistics (and severity distribution) per land-cover class.

    ``layer`` is a :class:`~earth_observation.landcover.LandCoverLayer`;
    statistics reuse :func:`~earth_observation.landcover.compute_class_stats`
    so the class thresholds and quality states are identical to the index
    stratification (valid fraction = paired-valid fraction of the class).
    """
    raise NotImplementedError


# --- pair selection ------------------------------------------------------------


class FireCandidate(BaseModel):
    result_kind: ResultKind = ResultKind.OBSERVATION
    acquisition_key: str
    primary_item_id: str
    contributing_item_ids: list[str]
    observed_at: datetime
    window: Literal["pre_fire", "post_fire"]
    cloud_cover_pct: float | None
    snow_ice_pct: float | None
    aoi_coverage_pct: float
    eligible: bool
    exclusion_reason: str | None = None
    days_from_event_edge: int = Field(
        description="Pre: days before the pre window end; post: days after the post window start"
    )


class RankedPair(BaseModel):
    rank: int
    pre_key: str
    post_key: str
    pre_observed_at: datetime
    post_observed_at: datetime
    seasonal_offset_days: int
    within_seasonal_tolerance: bool
    cloud_bucket: int
    snow_bucket: int
    max_cloud_cover_pct: float | None
    timing_offset_days: int
    days_between: int


class PairAttempt(BaseModel):
    rank: int
    pre_key: str
    post_key: str
    outcome: Literal["selected", "rejected"]
    reason: str | None = None
    paired_valid_pct: float | None = None


class FirePairPlan(BaseModel):
    """Ranked plan produced before any pixel is read."""

    algorithm: str = PAIR_SELECTION_ALGORITHM
    version: str = PAIR_SELECTION_VERSION
    parameters: dict[str, Any]
    candidates: list[FireCandidate]
    ranked_pairs: list[RankedPair]


def plan_fire_pairs(
    acquisitions: list[Acquisition],
    *,
    pre_window: tuple[date, date],
    post_window: tuple[date, date],
    max_cloud_cover_pct: float,
    min_aoi_coverage_pct: float,
    config: WildfireConfig,
) -> FirePairPlan:
    """Candidates with eligibility + every eligible pair ranked (module docstring).

    ``ranked_pairs`` holds ALL eligible pairs in rank order (the worker
    walks it); callers truncate to ``ranked_pairs_recorded`` when recording.
    """
    raise NotImplementedError


def seasonal_offset_days(a: datetime, b: datetime) -> int:
    """Circular day-of-year distance between two dates (leap-year aware, 0..183)."""
    raise NotImplementedError


# --- document ------------------------------------------------------------------


class WildfireDocument(BaseModel):
    """The ``wildfire_dnbr.json`` artifact (and API response body)."""

    schema_version: str = WILDFIRE_SCHEMA_VERSION
    workflow: str = "wildfire_dnbr"
    status: Literal["computed", "failed"]
    formula: str = DNBR_FORMULA
    sign_convention: str = DNBR_SIGN_CONVENTION
    mask_policy: str = DNBR_MASK_POLICY
    windows: dict[str, dict[str, str]]
    event: dict[str, Any] | None = None
    pair_selection: dict[str, Any] = Field(
        description="FirePairPlan (ranked pairs truncated) + attempts + selected pair"
    )
    pre_fire: NbrObservationStats | None = None
    post_fire: NbrObservationStats | None = None
    dnbr: DnbrStats | None = None
    severity: dict[str, Any] = Field(
        description='{"enabled": bool, "result_kind": "interpretation", "scheme": {...}, '
        '"distribution": [SeverityClassStats...], "note": str}'
    )
    land_cover: dict[str, Any] | None = Field(
        default=None,
        description='{"dataset": {...}, "reference_year": int, "selection_reason": str, '
        '"classes": [ClassDnbr...]} or None when land cover was unavailable/not requested',
    )
    quality: QualityInfo
    warnings: list[str] = Field(default_factory=list)
    interpretation_note: str = ""


def interpretation_note() -> str:
    """Standard statement distinguishing spectral from field-observed severity."""
    return (
        "dNBR quantifies the spectral change between the selected pre- and "
        "post-fire observations for pixels valid on both dates. Where severity "
        "classes are shown they are spectral classes under the named threshold "
        "scheme, not field-observed ecological or soil burn severity; confirming "
        "burn severity requires field assessment (e.g. Composite Burn Index plots) "
        "or independently validated products. dNBR alone does not establish that "
        "a fire caused the change."
    )


def wildfire_summary(document: WildfireDocument) -> dict[str, Any]:
    """Compact block stored in ``analysis.summary["wildfire"]``.

    Keys: ``status``, ``formula``, ``pre_fire`` / ``post_fire`` (item id,
    observed_at, mean NBR), ``seasonal_offset_days``, ``dnbr`` (mean, median,
    p90, paired_valid_pct, paired_valid_area_km2, quality_state),
    ``severity`` (enabled, scheme_id, distribution as key/label/pct/area_km2),
    ``quality_state``.
    """
    raise NotImplementedError


def _finite(value: float) -> float | None:
    """``None`` for NaN/inf so JSON never carries non-finite numbers."""
    return value if math.isfinite(value) else None
