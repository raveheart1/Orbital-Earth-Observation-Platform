"""Tests for multi-year support: windowed catalog search and seasonal selection.

Two defects motivated these, both found by probing real data:

1. A single STAC query is capped at ``max_items`` and returns catalog order, so
   asking for 2018-2026 silently searched only 2022-2026 — the user would
   believe they analysed 8 years and actually got 4.
2. Spreading N scenes evenly over several years picks arbitrary months
   (June, February, April, ...). In a temperate region the seasonal NDVI swing
   (~0.15 to ~0.85) dwarfs any multi-year trend (~0.02-0.05), so such a series
   mostly measures which month each scene fell in.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest

from earth_observation.acquisition import Acquisition
from earth_observation.selection import (
    REASON_CLOUD,
    REASON_COVERAGE,
    REASON_OUTSIDE_SEASON,
    REASON_YEAR_SAMPLED_OUT,
    SEASONAL_ALGORITHM,
    SelectionStrategy,
    _day_of_year_distance,
    select_acquisitions_seasonal,
)
from earth_observation.stac import _split_range
from earth_observation.testing import make_metadata_candidate


def acquisition_on(when: datetime, cloud: float = 5.0, coverage: float = 100.0) -> Acquisition:
    candidate = make_metadata_candidate(when.isoformat(), 0, cloud, overlap=coverage)
    candidate = candidate.model_copy(update={"observed_at": when})
    return Acquisition(
        key=f"acq-{when.isoformat()}",
        observed_at=when,
        platform="sentinel-2a",
        relative_orbit="R040",
        collection="sentinel-2-l2a",
        granules=[candidate],
        aoi_coverage_pct=coverage,
    )


class TestSearchWindowing:
    def test_short_range_is_a_single_window(self):
        assert _split_range("2024-06-01", "2024-08-31", 370) == [("2024-06-01", "2024-08-31")]

    def test_long_range_is_split(self):
        windows = _split_range("2018-01-01", "2026-06-30", 370)
        assert len(windows) > 1

    def test_windows_cover_the_whole_range_without_gaps_or_overlap(self):
        windows = _split_range("2018-01-01", "2026-06-30", 370)
        assert windows[0][0] == "2018-01-01"
        assert windows[-1][1] == "2026-06-30"
        for (_, prev_end), (next_start, _) in pairwise(windows):
            gap = datetime.fromisoformat(next_start) - datetime.fromisoformat(prev_end)
            assert gap == timedelta(days=1), "windows must be consecutive"

    def test_window_size_respects_the_cap(self):
        for start, end in _split_range("2015-07-01", "2026-06-30", 370):
            span = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days + 1
            assert span <= 370

    def test_reversed_range_rejected(self):
        from earth_observation.errors import UserInputError

        with pytest.raises(UserInputError):
            _split_range("2024-08-01", "2024-06-01", 370)


class TestDayOfYearDistance:
    def test_exact_match(self):
        assert _day_of_year_distance(datetime(2024, 7, 15, tzinfo=UTC), 7, 15) == 0

    def test_within_month(self):
        assert _day_of_year_distance(datetime(2024, 7, 5, tzinfo=UTC), 7, 15) == 10

    def test_wraps_around_the_year_boundary(self):
        """31 December is 2 days from 2 January, not 363."""
        assert _day_of_year_distance(datetime(2024, 12, 31, tzinfo=UTC), 1, 2) == 2

    def test_opposite_season_is_far(self):
        assert _day_of_year_distance(datetime(2024, 1, 15, tzinfo=UTC), 7, 15) > 150


class TestSeasonalSelection:
    def _years(self, months_days: list[tuple[int, int, int]], **kw) -> list[Acquisition]:
        return [acquisition_on(datetime(y, m, d, tzinfo=UTC), **kw) for y, m, d in months_days]

    def test_one_observation_per_year(self):
        acqs = self._years([(2020, 7, 3), (2020, 7, 20), (2021, 7, 8), (2022, 7, 12), (2023, 7, 5)])
        selection = select_acquisitions_seasonal(
            acqs,
            scene_limit=8,
            max_cloud_cover_pct=50.0,
            min_aoi_coverage_pct=99.0,
            target_month=7,
        )
        years = [a.observed_at.year for a in selection.selected]
        assert years == sorted(set(years)), "at most one observation per year"
        assert years == [2020, 2021, 2022, 2023]

    def test_all_observations_land_in_the_same_season(self):
        acqs = self._years([(2020, 7, 3), (2021, 7, 18), (2022, 6, 25), (2023, 8, 2)])
        selection = select_acquisitions_seasonal(
            acqs,
            scene_limit=8,
            max_cloud_cover_pct=50.0,
            min_aoi_coverage_pct=99.0,
            target_month=7,
            tolerance_days=30,
        )
        for a in selection.selected:
            assert _day_of_year_distance(a.observed_at, 7, 15) <= 30

    def test_out_of_season_excluded_with_reason(self):
        acqs = self._years([(2020, 7, 10), (2020, 2, 14)])
        selection = select_acquisitions_seasonal(
            acqs,
            scene_limit=8,
            max_cloud_cover_pct=50.0,
            min_aoi_coverage_pct=99.0,
            target_month=7,
            tolerance_days=30,
        )
        assert len(selection.selected) == 1
        assert selection.selected[0].observed_at.month == 7
        assert any(e.reason == REASON_OUTSIDE_SEASON for e in selection.excluded)

    def test_lowest_cloud_wins_within_a_year(self):
        clear = acquisition_on(datetime(2021, 7, 20, tzinfo=UTC), cloud=1.0)
        cloudy = acquisition_on(datetime(2021, 7, 15, tzinfo=UTC), cloud=18.0)
        selection = select_acquisitions_seasonal(
            [cloudy, clear],
            scene_limit=8,
            max_cloud_cover_pct=50.0,
            min_aoi_coverage_pct=99.0,
            target_month=7,
        )
        assert selection.selected[0].cloud_cover_pct == 1.0

    def test_coverage_and_cloud_gates_still_apply(self):
        acqs = [
            acquisition_on(datetime(2020, 7, 10, tzinfo=UTC), coverage=50.0),
            acquisition_on(datetime(2021, 7, 10, tzinfo=UTC), cloud=90.0),
            acquisition_on(datetime(2022, 7, 10, tzinfo=UTC)),
        ]
        selection = select_acquisitions_seasonal(
            acqs,
            scene_limit=8,
            max_cloud_cover_pct=20.0,
            min_aoi_coverage_pct=99.0,
            target_month=7,
        )
        assert [a.observed_at.year for a in selection.selected] == [2022]
        reasons = {e.reason for e in selection.excluded}
        assert REASON_COVERAGE in reasons
        assert REASON_CLOUD in reasons

    def test_year_subsampling_keeps_the_endpoints(self):
        """More years than the limit: keep a spread that still spans the range."""
        acqs = self._years([(y, 7, 10) for y in range(2016, 2027)])
        selection = select_acquisitions_seasonal(
            acqs,
            scene_limit=4,
            max_cloud_cover_pct=50.0,
            min_aoi_coverage_pct=99.0,
            target_month=7,
        )
        years = [a.observed_at.year for a in selection.selected]
        assert len(years) == 4
        assert years[0] == 2016, "first year kept so the series spans the range"
        assert years[-1] == 2026, "last year kept"
        assert any(e.reason == REASON_YEAR_SAMPLED_OUT for e in selection.excluded)

    def test_missing_year_is_simply_absent(self):
        """A year with nothing usable leaves a gap rather than a bad substitute."""
        acqs = self._years([(2020, 7, 10), (2022, 7, 10)])
        selection = select_acquisitions_seasonal(
            acqs,
            scene_limit=8,
            max_cloud_cover_pct=50.0,
            min_aoi_coverage_pct=99.0,
            target_month=7,
        )
        assert [a.observed_at.year for a in selection.selected] == [2020, 2022]

    def test_deterministic(self):
        acqs = self._years([(2020, 7, 3), (2021, 7, 18), (2022, 6, 25), (2023, 7, 2)])
        first = select_acquisitions_seasonal(
            acqs,
            scene_limit=3,
            max_cloud_cover_pct=50.0,
            min_aoi_coverage_pct=99.0,
            target_month=7,
        )
        second = select_acquisitions_seasonal(
            list(reversed(acqs)),
            scene_limit=3,
            max_cloud_cover_pct=50.0,
            min_aoi_coverage_pct=99.0,
            target_month=7,
        )
        assert [a.key for a in first.selected] == [a.key for a in second.selected]

    def test_records_algorithm_and_target(self):
        selection = select_acquisitions_seasonal(
            self._years([(2020, 7, 10)]),
            scene_limit=8,
            max_cloud_cover_pct=50.0,
            min_aoi_coverage_pct=99.0,
            target_month=7,
            tolerance_days=30,
        )
        assert selection.algorithm == SEASONAL_ALGORITHM
        assert selection.seasonal_target == {"month": 7, "day": 15, "tolerance_days": 30}

    def test_output_is_chronological(self):
        acqs = self._years([(2023, 7, 5), (2020, 7, 5), (2022, 7, 5)])
        selection = select_acquisitions_seasonal(
            acqs,
            scene_limit=8,
            max_cloud_cover_pct=50.0,
            min_aoi_coverage_pct=99.0,
            target_month=7,
        )
        times = [a.observed_at for a in selection.selected]
        assert times == sorted(times)


def test_strategy_enum_values():
    assert {s.value for s in SelectionStrategy} == {"temporal", "seasonal"}
