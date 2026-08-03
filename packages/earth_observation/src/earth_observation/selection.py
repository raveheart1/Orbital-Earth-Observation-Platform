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
from datetime import UTC, datetime

from earth_observation.acquisition import Acquisition

SCENE_SELECTION_ALGORITHM = "temporal-stratified-lowest-cloud"
SCENE_SELECTION_VERSION = "2.0.0"

REASON_COVERAGE = "insufficient_aoi_coverage"
REASON_CLOUD = "cloud_cover_above_threshold"
REASON_SAMPLED_OUT = "not_selected_temporal_sampling"


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
