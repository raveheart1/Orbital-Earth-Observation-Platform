"""Deterministic acquisition selection.

Selection operates on ACQUISITIONS (one observation instant, possibly backed by
several granules), not on individual STAC items. Selecting items directly is
what previously let a single granule covering 56 % of a tile-crossing AOI stand
in for a whole observation.

Strategy ``temporal-stratified-lowest-cloud`` v2.0.0:

1. Exclude acquisitions whose granules together cover less than
   ``min_aoi_coverage_pct`` of the AOI ("insufficient_aoi_coverage") — a
   partially covered date cannot be compared with a fully covered one.
2. Exclude acquisitions above the requested cloud-cover threshold
   ("cloud_cover_above_threshold").
3. If the survivors fit within the limit, select them all.
4. Otherwise split the requested date range into ``limit`` equal time buckets
   and, within each, select the acquisition with the lowest
   (cloud_cover, observed_at, key) sort key — favouring low cloud while
   preserving temporal coverage.
5. Fill any slots left by empty buckets with the lowest-cloud unselected
   survivors, in the same deterministic order.

Every excluded acquisition is recorded with its reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum

from earth_observation.acquisition import Acquisition

SCENE_SELECTION_ALGORITHM = "temporal-stratified-lowest-cloud"
SCENE_SELECTION_VERSION = "2.0.0"

SEASONAL_ALGORITHM = "seasonal-same-window-lowest-cloud"
SEASONAL_VERSION = "1.0.0"

REASON_COVERAGE = "insufficient_aoi_coverage"
REASON_CLOUD = "cloud_cover_above_threshold"
REASON_SAMPLED_OUT = "not_selected_temporal_sampling"
REASON_OUTSIDE_SEASON = "outside_seasonal_window"
REASON_YEAR_SAMPLED_OUT = "not_selected_year_sampling"


class SelectionStrategy(str, Enum):
    """How observations are chosen from the candidate acquisitions.

    ``TEMPORAL`` spreads scenes evenly over the requested range — good for
    watching one growing season. ``SEASONAL`` takes one scene per year from
    the same part of the calendar — the only sound way to compare across
    years, because in a temperate region the seasonal NDVI swing (~0.15 to
    ~0.85) dwarfs any multi-year trend, so an evenly-spread series mostly
    measures which month each scene happened to land in.
    """

    TEMPORAL = "temporal"
    SEASONAL = "seasonal"


@dataclass
class ExcludedAcquisition:
    acquisition: Acquisition
    reason: str


@dataclass
class AcquisitionSelection:
    selected: list[Acquisition]
    excluded: list[ExcludedAcquisition] = field(default_factory=list)
    algorithm: str = SCENE_SELECTION_ALGORITHM
    algorithm_version: str = SCENE_SELECTION_VERSION
    #: Populated by the seasonal strategy so provenance records the target.
    seasonal_target: dict[str, int] | None = None


def _sort_key(acquisition: Acquisition) -> tuple[float, datetime, str]:
    cloud = acquisition.cloud_cover_pct
    return (cloud if cloud is not None else 101.0, acquisition.observed_at, acquisition.key)


def select_acquisitions(
    acquisitions: list[Acquisition],
    *,
    scene_limit: int,
    max_cloud_cover_pct: float,
    min_aoi_coverage_pct: float,
    range_start: datetime,
    range_end: datetime,
) -> AcquisitionSelection:
    """Apply the documented deterministic selection strategy."""
    excluded: list[ExcludedAcquisition] = []
    survivors: list[Acquisition] = []

    for acquisition in acquisitions:
        if acquisition.aoi_coverage_pct < min_aoi_coverage_pct:
            excluded.append(ExcludedAcquisition(acquisition, REASON_COVERAGE))
            continue
        cloud = acquisition.cloud_cover_pct
        if cloud is not None and cloud > max_cloud_cover_pct:
            excluded.append(ExcludedAcquisition(acquisition, REASON_CLOUD))
            continue
        survivors.append(acquisition)

    if len(survivors) <= scene_limit:
        return AcquisitionSelection(
            selected=sorted(survivors, key=lambda a: (a.observed_at, a.key)),
            excluded=excluded,
        )

    if range_start.tzinfo is None:
        range_start = range_start.replace(tzinfo=UTC)
    if range_end.tzinfo is None:
        range_end = range_end.replace(tzinfo=UTC)
    span_seconds = max((range_end - range_start).total_seconds(), 1.0)
    bucket_seconds = span_seconds / scene_limit

    buckets: dict[int, list[Acquisition]] = {}
    for acquisition in survivors:
        observed = acquisition.observed_at
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        index = int((observed - range_start).total_seconds() // bucket_seconds)
        index = min(max(index, 0), scene_limit - 1)
        buckets.setdefault(index, []).append(acquisition)

    selected_keys: set[str] = set()
    selected: list[Acquisition] = []
    for index in sorted(buckets):
        best = min(buckets[index], key=_sort_key)
        selected.append(best)
        selected_keys.add(best.key)

    if len(selected) < scene_limit:
        leftovers = sorted((a for a in survivors if a.key not in selected_keys), key=_sort_key)
        for acquisition in leftovers[: scene_limit - len(selected)]:
            selected.append(acquisition)
            selected_keys.add(acquisition.key)

    for acquisition in survivors:
        if acquisition.key not in selected_keys:
            excluded.append(ExcludedAcquisition(acquisition, REASON_SAMPLED_OUT))

    selected.sort(key=lambda a: (a.observed_at, a.key))
    return AcquisitionSelection(selected=selected, excluded=excluded)


def _day_of_year_distance(observed: datetime, target_month: int, target_day: int) -> int:
    """Smallest distance in days between an observation and a target date.

    Wraps around the year boundary, so 31 December is 2 days from 2 January
    rather than 363 — otherwise a January target would reject December scenes
    for the wrong reason.
    """
    try:
        target = date(observed.year, target_month, target_day)
    except ValueError:  # 29 February in a common year
        target = date(observed.year, target_month, target_day - 1)
    diff = abs((observed.date() - target).days)
    # Use the observation year's ACTUAL length: with a hardcoded 365 the wrap
    # distance is off by one in leap years.
    year_length = (date(observed.year + 1, 1, 1) - date(observed.year, 1, 1)).days
    return min(diff, year_length - diff)


def select_acquisitions_seasonal(
    acquisitions: list[Acquisition],
    *,
    scene_limit: int,
    max_cloud_cover_pct: float,
    min_aoi_coverage_pct: float,
    target_month: int,
    target_day: int = 15,
    tolerance_days: int = 30,
) -> AcquisitionSelection:
    """Select one acquisition per year from the same part of the calendar.

    Strategy ``seasonal-same-window-lowest-cloud`` v1.0.0:

    1. Exclude acquisitions below the AOI-coverage threshold, then those above
       the cloud threshold (same gates as the temporal strategy).
    2. Exclude acquisitions further than ``tolerance_days`` from the target
       day-of-year ("outside_seasonal_window"). This is what holds phenology
       roughly constant so a year-to-year difference reflects the surface
       rather than the season.
    3. Group the survivors by calendar year and take, per year, the lowest
       ``(cloud_cover, |day offset|, key)`` — cloud dominates because cloud
       contamination is the larger threat to the measurement, with proximity
       to the target date breaking ties.
    4. If more years survive than ``scene_limit``, keep an evenly spaced
       subset spanning the full range (always including the first and last
       year) so the series still covers the whole period.

    Deterministic: identical inputs always produce identical output.
    """
    excluded: list[ExcludedAcquisition] = []
    survivors: list[Acquisition] = []

    for acquisition in acquisitions:
        if acquisition.aoi_coverage_pct < min_aoi_coverage_pct:
            excluded.append(ExcludedAcquisition(acquisition, REASON_COVERAGE))
            continue
        cloud = acquisition.cloud_cover_pct
        if cloud is not None and cloud > max_cloud_cover_pct:
            excluded.append(ExcludedAcquisition(acquisition, REASON_CLOUD))
            continue
        if (
            _day_of_year_distance(acquisition.observed_at, target_month, target_day)
            > tolerance_days
        ):
            excluded.append(ExcludedAcquisition(acquisition, REASON_OUTSIDE_SEASON))
            continue
        survivors.append(acquisition)

    by_year: dict[int, list[Acquisition]] = {}
    for acquisition in survivors:
        by_year.setdefault(acquisition.observed_at.year, []).append(acquisition)

    def seasonal_key(acquisition: Acquisition) -> tuple[float, int, str]:
        cloud = acquisition.cloud_cover_pct
        return (
            cloud if cloud is not None else 101.0,
            _day_of_year_distance(acquisition.observed_at, target_month, target_day),
            acquisition.key,
        )

    best_per_year = {year: min(items, key=seasonal_key) for year, items in by_year.items()}
    years = sorted(best_per_year)

    if len(years) > scene_limit:
        # Evenly spaced years across the full range, endpoints always kept.
        if scene_limit == 1:
            keep_indices = [len(years) - 1]
        else:
            step = (len(years) - 1) / (scene_limit - 1)
            keep_indices = sorted({round(i * step) for i in range(scene_limit)})
        keep_years = {years[i] for i in keep_indices}
    else:
        keep_years = set(years)

    selected = [best_per_year[y] for y in years if y in keep_years]
    selected_keys = {a.key for a in selected}
    for acquisition in survivors:
        if acquisition.key not in selected_keys:
            year_dropped = acquisition.observed_at.year not in keep_years
            excluded.append(
                ExcludedAcquisition(
                    acquisition,
                    REASON_YEAR_SAMPLED_OUT if year_dropped else REASON_SAMPLED_OUT,
                )
            )

    selected.sort(key=lambda a: (a.observed_at, a.key))
    return AcquisitionSelection(
        selected=selected,
        excluded=excluded,
        algorithm=SEASONAL_ALGORITHM,
        algorithm_version=SEASONAL_VERSION,
        seasonal_target={
            "month": target_month,
            "day": target_day,
            "tolerance_days": tolerance_days,
        },
    )
