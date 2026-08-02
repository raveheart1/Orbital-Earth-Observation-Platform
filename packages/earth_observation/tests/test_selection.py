"""Deterministic scene-selection tests."""

from __future__ import annotations

from earth_observation.selection import select_scenes
from earth_observation.testing import (
    SELECTION_RANGE_END as END,
)
from earth_observation.testing import (
    SELECTION_RANGE_START as START,
)
from earth_observation.testing import (
    make_metadata_candidate as make,
)


def run(candidates, limit=4, max_cloud=20.0, min_overlap=25.0):
    return select_scenes(
        candidates,
        scene_limit=limit,
        max_cloud_cover_pct=max_cloud,
        min_aoi_overlap_pct=min_overlap,
        range_start=START,
        range_end=END,
    )


def test_all_selected_when_under_limit():
    selection = run([make("a", 1, 5), make("b", 40, 8)], limit=4)
    assert [c.item_id for c in selection.selected] == ["a", "b"]
    assert selection.excluded == []


def test_overlap_filter_excludes_with_reason():
    selection = run([make("a", 1, 5), make("edge", 2, 5, overlap=10.0)])
    assert [c.item_id for c in selection.selected] == ["a"]
    assert selection.excluded[0].candidate.item_id == "edge"
    assert selection.excluded[0].reason == "insufficient_aoi_overlap"


def test_cloud_filter_excludes_with_reason():
    selection = run([make("a", 1, 5), make("cloudy", 2, 55.0)])
    assert [c.item_id for c in selection.selected] == ["a"]
    assert selection.excluded[0].reason == "cloud_cover_above_threshold"


def test_temporal_stratification_prefers_low_cloud_per_bucket():
    # Two candidates in the same month-bucket: lower cloud must win.
    candidates = [
        make("may_clear", 5, 2.0),
        make("may_hazy", 10, 15.0),
        make("jun", 45, 5.0),
        make("jul", 75, 5.0),
        make("aug", 105, 5.0),
        make("aug2", 110, 1.0),
    ]
    selection = run(candidates, limit=4)
    ids = [c.item_id for c in selection.selected]
    assert len(ids) == 4
    assert "may_clear" in ids
    assert "may_hazy" not in ids
    sampled_out = {e.candidate.item_id for e in selection.excluded}
    assert "may_hazy" in sampled_out
    assert all(e.reason == "not_selected_temporal_sampling" for e in selection.excluded)


def test_selection_is_deterministic():
    candidates = [make(f"s{i}", i * 3, (i * 7) % 19) for i in range(30)]
    first = run(candidates, limit=6)
    second = run(list(reversed(candidates)), limit=6)
    assert [c.item_id for c in first.selected] == [c.item_id for c in second.selected]


def test_selected_output_is_chronological():
    candidates = [make("late", 100, 1.0), make("early", 2, 1.0), make("mid", 50, 1.0)]
    selection = run(candidates, limit=3)
    times = [c.observed_at for c in selection.selected]
    assert times == sorted(times)


def test_empty_input():
    selection = run([])
    assert selection.selected == []
    assert selection.excluded == []


def test_every_candidate_accounted_for():
    candidates = [make(f"s{i}", i * 4, float(i)) for i in range(20)]
    selection = run(candidates, limit=5)
    accounted = {c.item_id for c in selection.selected} | {
        e.candidate.item_id for e in selection.excluded
    }
    assert accounted == {c.item_id for c in candidates}
    assert len(selection.selected) == 5


def test_none_cloud_cover_sorts_last():
    a = make("known", 5, 3.0)
    b = make("unknown", 6, 0.0)
    b = b.model_copy(update={"cloud_cover_pct": None})
    selection = run([a, b], limit=1)
    assert [c.item_id for c in selection.selected] == ["known"]


def test_algorithm_metadata_recorded():
    selection = run([make("a", 1, 5)])
    assert selection.algorithm == "temporal-stratified-lowest-cloud"
    assert selection.algorithm_version == "1.0.0"
