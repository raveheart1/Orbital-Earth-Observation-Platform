"""Deterministic acquisition-selection tests."""

from __future__ import annotations

from earth_observation.acquisition import Acquisition
from earth_observation.selection import (
    REASON_CLOUD,
    REASON_COVERAGE,
    REASON_SAMPLED_OUT,
    select_acquisitions,
)
from earth_observation.testing import (
    SELECTION_RANGE_END as END,
)
from earth_observation.testing import (
    SELECTION_RANGE_START as START,
)
from earth_observation.testing import (
    make_metadata_candidate,
)


def make(key: str, days: int, cloud: float, coverage: float = 100.0) -> Acquisition:
    """One acquisition backed by a single synthetic granule."""
    candidate = make_metadata_candidate(key, days, cloud, overlap=coverage)
    return Acquisition(
        key=key,
        observed_at=candidate.observed_at,
        platform=candidate.platform,
        relative_orbit="R040",
        collection=candidate.collection,
        granules=[candidate],
        aoi_coverage_pct=coverage,
    )


def run(acquisitions, limit=4, max_cloud=20.0, min_coverage=99.0):
    return select_acquisitions(
        acquisitions,
        scene_limit=limit,
        max_cloud_cover_pct=max_cloud,
        min_aoi_coverage_pct=min_coverage,
        range_start=START,
        range_end=END,
    )


def test_all_selected_when_under_limit():
    selection = run([make("a", 1, 5), make("b", 40, 8)], limit=4)
    assert [a.key for a in selection.selected] == ["a", "b"]
    assert selection.excluded == []


def test_partial_coverage_excluded_with_reason():
    selection = run([make("full", 1, 5), make("partial", 2, 5, coverage=56.2)])
    assert [a.key for a in selection.selected] == ["full"]
    assert selection.excluded[0].acquisition.key == "partial"
    assert selection.excluded[0].reason == REASON_COVERAGE


def test_coverage_threshold_is_applied_not_hardcoded():
    acquisitions = [make("a", 1, 5, coverage=95.0)]
    assert run(acquisitions, min_coverage=99.0).selected == []
    assert len(run(acquisitions, min_coverage=90.0).selected) == 1


def test_cloud_filter_excludes_with_reason():
    selection = run([make("a", 1, 5), make("cloudy", 2, 55.0)])
    assert [a.key for a in selection.selected] == ["a"]
    assert selection.excluded[0].reason == REASON_CLOUD


def test_temporal_stratification_prefers_low_cloud_per_bucket():
    acquisitions = [
        make("may_clear", 5, 2.0),
        make("may_hazy", 10, 15.0),
        make("jun", 45, 5.0),
        make("jul", 75, 5.0),
        make("aug", 105, 5.0),
        make("aug2", 110, 1.0),
    ]
    selection = run(acquisitions, limit=4)
    keys = [a.key for a in selection.selected]
    assert len(keys) == 4
    assert "may_clear" in keys
    assert "may_hazy" not in keys
    assert all(e.reason == REASON_SAMPLED_OUT for e in selection.excluded)


def test_selection_is_deterministic():
    acquisitions = [make(f"s{i}", i * 3, (i * 7) % 19) for i in range(30)]
    first = run(acquisitions, limit=6)
    second = run(list(reversed(acquisitions)), limit=6)
    assert [a.key for a in first.selected] == [a.key for a in second.selected]


def test_selected_output_is_chronological():
    selection = run([make("late", 100, 1.0), make("early", 2, 1.0), make("mid", 50, 1.0)])
    times = [a.observed_at for a in selection.selected]
    assert times == sorted(times)


def test_empty_input():
    selection = run([])
    assert selection.selected == []
    assert selection.excluded == []


def test_every_acquisition_accounted_for():
    acquisitions = [make(f"s{i}", i * 4, float(i)) for i in range(20)]
    selection = run(acquisitions, limit=5)
    accounted = {a.key for a in selection.selected} | {
        e.acquisition.key for e in selection.excluded
    }
    assert accounted == {a.key for a in acquisitions}
    assert len(selection.selected) == 5


def test_none_cloud_cover_sorts_last():
    known = make("known", 5, 3.0)
    unknown = make("unknown", 6, 0.0)
    unknown.granules[0] = unknown.granules[0].model_copy(update={"cloud_cover_pct": None})
    selection = run([known, unknown], limit=1)
    assert [a.key for a in selection.selected] == ["known"]


def test_algorithm_metadata_recorded():
    selection = run([make("a", 1, 5)])
    assert selection.algorithm == "temporal-stratified-lowest-cloud"
    assert selection.algorithm_version == "2.0.0"
