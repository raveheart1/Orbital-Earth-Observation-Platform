"""Temporal context: seasonal baselines, anomalies, trends, and phenology.

Raw differences between dates are dominated by the seasonal cycle: an April
vs July NDVI difference is green-up, not degradation or recovery. Temporal
context answers a different question — *is this observation unusual for this
place at this time of year?* — by comparing each observation against
seasonally comparable observations from a fixed historical reference period,
and estimates long-term monotonic change only with a method that compares
like seasons with like.

Methods (all deterministic; see docs/temporal-context.md)
---------------------------------------------------------
Reference period
    The ``baseline_years`` full calendar years immediately preceding the
    calendar year of the analysis start (e.g. an analysis starting
    2024-04-01 with 5 baseline years uses 2019-2023), clamped to the archive
    start. Fixed per analysis, so every observation of an analysis is
    compared with the same reference.

Historical sampling (``historical-monthly-lowest-cloud`` v1.0.0)
    Acquisitions in the reference period that pass the same coverage and
    cloud gates as analysis observations, restricted to calendar months that
    are seasonally relevant to the analysis's observation dates, one per
    (year, month) — the lowest cloud cover, ties by date then key. Above the
    cap, (year, month) slots are kept in order of seasonal relevance, then
    most recent year first.

Baseline (``doy-window-year-median`` v1.0.0)
    For a target observation, the comparable sample is every eligible
    historical observation within ``baseline_window_days`` of the target's
    day of year (circular, leap-year aware). Each reference year contributes
    ONE value — the median of its comparable observations — so a year with
    six clear scenes cannot outvote a year with one. Expected value = median
    of the year values; spread = MAD (and 1.4826 x MAD as a robust sigma),
    IQR, and range of the year values.

Anomaly (``robust-z-mad`` v1.0.0)
    absolute = observed - expected. The robust standardized anomaly
    (observed - expected) / (1.4826 x MAD) and the unusually low/high
    classification are reported only when the baseline has at least
    ``standardized_min_years`` years and a robust sigma above
    ``min_robust_sigma``; the relative anomaly only when |expected| is large
    enough for a percentage to mean something.

Trend (``seasonal-kendall-sen`` v1.0.0)
    Seasonal Kendall test (Hirsch, Slack & Smith 1982) with calendar months
    as seasons: one value per (year, month), Mann-Kendall S within each
    month, summed across months, tie-corrected variance, continuity-
    corrected normal approximation for the two-sided p-value; slope = median
    of all within-season pairwise slopes (seasonal Sen slope) with the
    Gilbert (1987) rank-based confidence interval. Because only same-season
    values are ever compared, a seasonal cycle alone produces no trend.
    Serial correlation between years is NOT corrected (documented
    assumption).

Phenology (``observed-annual-extremes`` v1.0.0)
    Per year with dense enough sampling: observed maximum and its date
    (approximate peak timing, with an uncertainty of half the larger
    neighbouring gap), and minimum/amplitude WITHIN THE SAMPLED MONTHS only.
    No start/end-of-season dates are derived.

Nothing here interpolates between observations or fills a gap. Every result
that cannot be supported by the data carries a structured quality state and
``None`` values.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from earth_observation.acquisition import Acquisition
from earth_observation.quality import QualityInfo, ResultKind
from earth_observation.selection import AcquisitionSelection
from earth_observation.types import SceneResult, TemporalConfig

TEMPORAL_SCHEMA_VERSION = "1.0.0"

HISTORICAL_SELECTION_ALGORITHM = "historical-monthly-lowest-cloud"
HISTORICAL_SELECTION_VERSION = "1.0.0"
BASELINE_METHOD = "doy-window-year-median"
BASELINE_VERSION = "1.0.0"
ANOMALY_METHOD = "robust-z-mad"
ANOMALY_VERSION = "1.0.0"
TREND_METHOD = "seasonal-kendall-sen"
TREND_VERSION = "1.0.0"
PHENOLOGY_METHOD = "observed-annual-extremes"
PHENOLOGY_VERSION = "1.0.0"

#: Consistency constant: 1.4826 x MAD estimates sigma for normal data.
MAD_TO_SIGMA = 1.4826

#: Exclusion reasons for historical candidates (recorded in provenance).
REASON_COVERAGE = "insufficient_aoi_coverage"
REASON_CLOUD = "cloud_cover_above_threshold"
REASON_OUTSIDE_REFERENCE = "outside_reference_period"
REASON_OUTSIDE_SEASON = "outside_seasonal_window"
REASON_SAMPLED_OUT = "not_selected_monthly_sampling"
REASON_BASELINE_CAP = "not_selected_baseline_cap"

#: Sample exclusion reasons (per stratum).
SAMPLE_CLOUD_CONTAMINATED = "valid_fraction_below_threshold"
SAMPLE_NO_STATISTICS = "stratum_statistics_unavailable"

AOI_STRATUM = "aoi"

AnomalyClassification = Literal[
    "unusually_low", "unusually_high", "within_typical_range", "not_assessed"
]


def class_stratum(code: int) -> str:
    """Stratum id of a land-cover class, e.g. ``class:10``."""
    return f"class:{code}"


class ReferencePeriod(BaseModel):
    start: date
    end: date
    requested_years: int
    years: list[int]
    archive_limited: bool = Field(
        description="True when the archive start clamped the requested period"
    )
    note: str = ""


class SeriesSample(BaseModel):
    """One stratum's measured value at one acquisition (an actual observation).

    ``value`` is the spatial MEAN of the stratum's valid pixels — the same
    statistic the time series reports. ``eligible`` is False when the value is
    missing or the stratum's valid fraction is below
    ``TemporalConfig.min_valid_fraction``; ineligible samples are shown but
    never used in a baseline or trend.
    """

    acquisition_key: str
    primary_item_id: str
    observed_at: datetime
    source: Literal["analysis", "historical"]
    value: float | None
    valid_fraction: float
    valid_pixel_count: int
    eligible: bool
    exclusion_reason: str | None = None


class YearValue(BaseModel):
    year: int
    median: float
    n_samples: int


class BaselineEstimate(BaseModel):
    method: str = BASELINE_METHOD
    version: str = BASELINE_VERSION
    window_days: int
    expected: float | None = Field(description="Median of per-year medians")
    n_samples: int = Field(description="Comparable historical observations")
    n_years: int = Field(description="Distinct reference years contributing")
    year_values: list[YearValue] = Field(default_factory=list)
    mad: float | None = Field(default=None, description="Median absolute deviation of year values")
    robust_sigma: float | None = Field(default=None, description="1.4826 x MAD")
    iqr_low: float | None = None
    iqr_high: float | None = None
    range_low: float | None = None
    range_high: float | None = None
    quality: QualityInfo


class AnomalyResult(BaseModel):
    result_kind: ResultKind = ResultKind.STATISTICAL_INFERENCE
    acquisition_key: str
    primary_item_id: str
    observed_at: datetime
    observed: float | None
    expected: float | None
    absolute_anomaly: float | None
    relative_anomaly_pct: float | None
    robust_z: float | None
    classification: AnomalyClassification
    baseline: BaselineEstimate
    quality: QualityInfo


class TrendResult(BaseModel):
    result_kind: ResultKind = ResultKind.STATISTICAL_INFERENCE
    method: str = TREND_METHOD
    version: str = TREND_VERSION
    computed: bool
    units: str = Field(description='e.g. "NDVI units per year"')
    slope_per_year: float | None = None
    slope_ci_low: float | None = None
    slope_ci_high: float | None = None
    confidence_level: float
    kendall_s: int | None = None
    variance_s: float | None = None
    z: float | None = None
    p_value: float | None = None
    alpha: float
    significant: bool | None = None
    n_observations: int = Field(description="Eligible observations entering the test")
    n_season_years: int = Field(description="(year, month) values after per-cell medians")
    n_years: int
    seasons_used: list[int] = Field(default_factory=list)
    first_observation: datetime | None = None
    last_observation: datetime | None = None
    span_years: float | None = None
    assumptions: list[str] = Field(default_factory=list)
    quality: QualityInfo
    interpretation_note: str = ""


class PhenologyYear(BaseModel):
    result_kind: ResultKind = ResultKind.MEASUREMENT
    year: int
    n_observations: int
    months_sampled: list[int]
    max_gap_days: int | None
    observed_max: float | None = None
    observed_max_date: date | None = None
    peak_doy: int | None = None
    peak_timing_uncertainty_days: int | None = None
    observed_min: float | None = None
    observed_min_date: date | None = None
    amplitude: float | None = None
    quality: QualityInfo
    note: str = ""


class StratumContext(BaseModel):
    stratum: str
    label: str
    class_code: int | None = None
    color: str | None = None
    samples: list[SeriesSample]
    anomalies: list[AnomalyResult]
    trend: TrendResult
    phenology: list[PhenologyYear]
    quality: QualityInfo


class HistoricalAcquisitionRecord(BaseModel):
    acquisition_key: str
    primary_item_id: str
    contributing_item_ids: list[str]
    observed_at: datetime
    cloud_cover_pct: float | None
    usable: bool
    unusable_reason: str | None = None
    cache_key: str | None = None
    cache_hit: bool = False


class HistoricalExclusion(BaseModel):
    acquisition_key: str
    primary_item_id: str
    observed_at: datetime
    reason: str


class HistoricalSelectionRecord(BaseModel):
    algorithm: str = HISTORICAL_SELECTION_ALGORITHM
    version: str = HISTORICAL_SELECTION_VERSION
    window_days: int
    relevant_months: list[int]
    max_acquisitions: int
    candidate_count: int
    selected: list[HistoricalAcquisitionRecord]
    excluded: list[HistoricalExclusion]
    search: dict[str, Any] = Field(default_factory=dict)


class TemporalContextDocument(BaseModel):
    """The ``temporal_context.json`` artifact (and API response body)."""

    schema_version: str = TEMPORAL_SCHEMA_VERSION
    result_kind: ResultKind = ResultKind.STATISTICAL_INFERENCE
    operation: str
    index_title: str
    status: Literal["computed", "skipped"]
    skipped_reason: str | None = None
    reference_period: ReferencePeriod | None = None
    historical_selection: HistoricalSelectionRecord | None = None
    methods: dict[str, dict[str, Any]] = Field(default_factory=dict)
    land_cover_dataset: str | None = None
    strata: list[StratumContext] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    interpretation_note: str = ""


# --- reference period and historical sampling --------------------------------


def reference_period(
    analysis_start: date, baseline_years: int, archive_start: date
) -> ReferencePeriod:
    """The fixed reference period (see module docstring)."""
    raise NotImplementedError


def relevant_months(target_dates: list[date], window_days: int) -> list[int]:
    """Calendar months (1-12) that can hold observations comparable to a target.

    Month ``m`` is relevant when some day of ``m`` lies within
    ``window_days`` (circular day-of-year distance) of some target date.
    Sorted ascending.
    """
    raise NotImplementedError


def select_historical_acquisitions(
    acquisitions: list[Acquisition],
    *,
    period: ReferencePeriod,
    target_dates: list[date],
    max_cloud_cover_pct: float,
    min_aoi_coverage_pct: float,
    window_days: int,
    max_acquisitions: int,
) -> AcquisitionSelection:
    """``historical-monthly-lowest-cloud`` v1.0.0 (module docstring).

    Every non-selected acquisition is recorded with one of the ``REASON_*``
    codes. Returns an :class:`AcquisitionSelection` with ``algorithm`` /
    ``algorithm_version`` set to this strategy; ``selected`` sorted by
    (observed_at, key). Deterministic.
    """
    raise NotImplementedError


# --- series extraction --------------------------------------------------------


def series_from_results(
    results: list[SceneResult],
    *,
    source: Literal["analysis", "historical"],
    config: TemporalConfig,
) -> dict[str, list[SeriesSample]]:
    """Samples per stratum from processed acquisitions.

    Usable results only. The ``aoi`` stratum uses ``stats.ndvi_mean`` and
    ``valid_pixel_count / aoi_pixel_count``; each land-cover class uses its
    :class:`ClassStats` ``mean`` / ``valid_fraction`` (classes whose stats
    are withheld yield ``value=None``, ``eligible=False``,
    ``exclusion_reason=SAMPLE_NO_STATISTICS``). Samples sorted by date.
    """
    raise NotImplementedError


# --- inference ------------------------------------------------------------------


def compute_baseline(
    target_observed_at: datetime,
    history: list[SeriesSample],
    config: TemporalConfig,
) -> BaselineEstimate:
    """``doy-window-year-median`` baseline for one target date.

    ``history`` holds historical samples of ONE stratum; only eligible
    samples are used. Quality: fewer than ``baseline_min_years`` distinct
    years → ``insufficient_history``; fewer than ``baseline_min_samples``
    samples → ``insufficient_samples``; ``expected`` is ``None`` in both.
    """
    raise NotImplementedError


def compute_anomaly(
    target: SeriesSample,
    history: list[SeriesSample],
    config: TemporalConfig,
) -> AnomalyResult:
    """Anomaly of one analysis observation against its seasonal baseline.

    An ineligible target (cloud-contaminated or missing) is ``not_assessed``
    with state ``cloud_contaminated`` (or ``insufficient_coverage`` when the
    value is missing) and no anomaly values.
    """
    raise NotImplementedError


def seasonal_kendall_trend(
    samples: list[SeriesSample],
    config: TemporalConfig,
    *,
    units: str,
) -> TrendResult:
    """Seasonal Kendall test + seasonal Sen slope over eligible samples.

    ``computed`` is False (with ``insufficient_history`` /
    ``insufficient_samples``) below ``trend_min_years`` distinct years or
    ``trend_min_season_years`` season-year values, or when no month has two
    or more years. Slopes are per year, time measured in decimal years.
    """
    raise NotImplementedError


def phenology_by_year(samples: list[SeriesSample], config: TemporalConfig) -> list[PhenologyYear]:
    """Observed annual extremes for every year present in ``samples`` (eligible only)."""
    raise NotImplementedError


# --- document -----------------------------------------------------------------


def method_descriptors(config: TemporalConfig) -> dict[str, dict[str, Any]]:
    """Name, version, description, parameters, and assumptions of every method."""
    raise NotImplementedError


def build_temporal_context(
    *,
    operation: str,
    index_title: str,
    units: str,
    analysis_results: list[SceneResult],
    historical_results: list[SceneResult],
    period: ReferencePeriod,
    selection_record: HistoricalSelectionRecord,
    strata_labels: dict[str, tuple[str, int | None, str | None]],
    land_cover_dataset_id: str | None,
    config: TemporalConfig,
    warnings: list[str] | None = None,
) -> TemporalContextDocument:
    """Assemble the temporal-context document.

    ``strata_labels`` maps stratum id → ``(label, class_code, color)``; the
    ``aoi`` stratum is always first ("Entire AOI"), classes follow in the
    given order. Anomalies are computed for ANALYSIS samples against
    HISTORICAL samples; trend and phenology use both.
    """
    raise NotImplementedError


def skipped_temporal_context(
    *, operation: str, index_title: str, reason: str, note: str
) -> TemporalContextDocument:
    """A ``status="skipped"`` document (e.g. temporal context unsupported)."""
    raise NotImplementedError


def temporal_summary(document: TemporalContextDocument) -> dict[str, Any]:
    """Compact block stored in ``analysis.summary["temporal_context"]``.

    Keys: ``status``, ``skipped_reason``, ``reference_period`` (start/end/
    years), ``historical_acquisitions_used``, ``strata_count``,
    ``unusual_observation_count`` (all strata), and ``aoi`` with the AOI
    stratum's trend headline (``computed``, ``slope_per_year``,
    ``slope_ci_low``/``high``, ``p_value``, ``significant``, ``units``,
    ``quality_state``) and anomaly counts by classification.
    """
    raise NotImplementedError
