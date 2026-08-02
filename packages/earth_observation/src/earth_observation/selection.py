"""Deterministic scene selection.

When more candidate scenes match than the analysis scene limit, we must pick a
subset. The strategy (``temporal-stratified-lowest-cloud`` v1.0.0) is fully
deterministic and documented:

1. Exclude candidates whose footprint covers less than
   ``min_aoi_overlap_pct`` of the AOI ("insufficient_aoi_overlap").
2. Exclude candidates above the requested cloud-cover threshold — defensive,
   the STAC query already filters ("cloud_cover_above_threshold").
3. If the survivors fit within the limit, select them all.
4. Otherwise split the requested date range into ``limit`` equal time buckets
   and, within each bucket, select the candidate with the lowest
   (cloud_cover, observed_at, item_id) sort key. This favours low cloud cover
   while preserving temporal coverage across the whole range.
5. If some buckets are empty, remaining slots are filled with the lowest-cloud
   unselected survivors, in the same deterministic order.

Every excluded candidate is recorded with its reason.
"""

from __future__ import annotations

from datetime import UTC, datetime

from earth_observation import SCENE_SELECTION_ALGORITHM, SCENE_SELECTION_VERSION
from earth_observation.types import ExcludedScene, SceneCandidate, SceneSelection

_REASON_OVERLAP = "insufficient_aoi_overlap"
_REASON_CLOUD = "cloud_cover_above_threshold"
_REASON_SAMPLED_OUT = "not_selected_temporal_sampling"


def _sort_key(candidate: SceneCandidate) -> tuple[float, datetime, str]:
    cloud = candidate.cloud_cover_pct if candidate.cloud_cover_pct is not None else 101.0
    return (cloud, candidate.observed_at, candidate.item_id)


def select_scenes(
    candidates: list[SceneCandidate],
    *,
    scene_limit: int,
    max_cloud_cover_pct: float,
    min_aoi_overlap_pct: float,
    range_start: datetime,
    range_end: datetime,
) -> SceneSelection:
    """Apply the documented deterministic selection strategy."""
    excluded: list[ExcludedScene] = []
    survivors: list[SceneCandidate] = []

    for candidate in candidates:
        overlap = candidate.aoi_overlap_pct
        if overlap is not None and overlap < min_aoi_overlap_pct:
            excluded.append(ExcludedScene(candidate=candidate, reason=_REASON_OVERLAP))
            continue
        cloud = candidate.cloud_cover_pct
        if cloud is not None and cloud > max_cloud_cover_pct:
            excluded.append(ExcludedScene(candidate=candidate, reason=_REASON_CLOUD))
            continue
        survivors.append(candidate)

    if len(survivors) <= scene_limit:
        chronological = sorted(survivors, key=lambda c: (c.observed_at, c.item_id))
        return SceneSelection(
            selected=chronological,
            excluded=excluded,
            algorithm=SCENE_SELECTION_ALGORITHM,
            algorithm_version=SCENE_SELECTION_VERSION,
        )

    if range_start.tzinfo is None:
        range_start = range_start.replace(tzinfo=UTC)
    if range_end.tzinfo is None:
        range_end = range_end.replace(tzinfo=UTC)
    span_seconds = max((range_end - range_start).total_seconds(), 1.0)
    bucket_seconds = span_seconds / scene_limit

    buckets: dict[int, list[SceneCandidate]] = {}
    for candidate in survivors:
        observed = candidate.observed_at
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        index = int((observed - range_start).total_seconds() // bucket_seconds)
        index = min(max(index, 0), scene_limit - 1)
        buckets.setdefault(index, []).append(candidate)

    selected_ids: set[str] = set()
    selected: list[SceneCandidate] = []
    for index in sorted(buckets):
        best = min(buckets[index], key=_sort_key)
        selected.append(best)
        selected_ids.add(best.item_id)

    if len(selected) < scene_limit:
        leftovers = sorted((c for c in survivors if c.item_id not in selected_ids), key=_sort_key)
        for candidate in leftovers[: scene_limit - len(selected)]:
            selected.append(candidate)
            selected_ids.add(candidate.item_id)

    for candidate in survivors:
        if candidate.item_id not in selected_ids:
            excluded.append(ExcludedScene(candidate=candidate, reason=_REASON_SAMPLED_OUT))

    selected.sort(key=lambda c: (c.observed_at, c.item_id))
    return SceneSelection(
        selected=selected,
        excluded=excluded,
        algorithm=SCENE_SELECTION_ALGORITHM,
        algorithm_version=SCENE_SELECTION_VERSION,
    )
