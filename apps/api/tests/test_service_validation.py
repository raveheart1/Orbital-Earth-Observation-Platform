"""Server-side constraint enforcement tests (no database required)."""

from __future__ import annotations

from datetime import date

import pytest

from earth_observation.errors import UserInputError
from oeop_api.problem import ProblemException
from oeop_api.rate_limit import SubmissionRateLimiter
from oeop_api.schemas import AnalysisCreateRequest
from oeop_api.services.analysis_service import _validate_dates, _validate_scene_limit
from oeop_core.settings import Settings


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def request_for(start: str, end: str, scene_limit: int | None = None):
    return AnalysisCreateRequest(
        bbox=(-83.3, 42.5, -83.2, 42.6),
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        scene_limit=scene_limit,
    )


class TestDateValidation:
    def test_valid_range_passes(self):
        _validate_dates(request_for("2024-05-01", "2024-09-01"), make_settings())

    def test_reversed_dates_rejected(self):
        with pytest.raises(UserInputError, match="on or after"):
            _validate_dates(request_for("2024-09-01", "2024-05-01"), make_settings())

    def test_pre_archive_dates_rejected(self):
        with pytest.raises(UserInputError, match="archive"):
            _validate_dates(request_for("2001-01-01", "2001-06-01"), make_settings())

    def test_future_start_rejected(self):
        with pytest.raises(UserInputError, match="future"):
            _validate_dates(request_for("2099-01-01", "2099-06-01"), make_settings())

    def test_span_limit_enforced(self):
        with pytest.raises(UserInputError, match="exceeds the maximum"):
            _validate_dates(
                request_for("2018-01-01", "2024-01-01"),
                make_settings(max_date_span_days=365),
            )

    def test_demo_mode_tightens_span(self):
        settings = make_settings(demo_mode=True, demo_max_date_span_days=100)
        with pytest.raises(UserInputError):
            _validate_dates(request_for("2024-01-01", "2024-06-30"), settings)


class TestSceneLimit:
    def test_default_applied(self):
        settings = make_settings()
        assert (
            _validate_scene_limit(request_for("2024-05-01", "2024-06-01"), settings)
            == settings.default_scene_limit
        )

    def test_over_limit_rejected(self):
        settings = make_settings(max_scene_limit=8)
        with pytest.raises(UserInputError, match="maximum"):
            _validate_scene_limit(request_for("2024-05-01", "2024-06-01", scene_limit=50), settings)


class TestRateLimiter:
    def test_allows_up_to_limit_then_429(self):
        limiter = SubmissionRateLimiter(3)
        for _ in range(3):
            limiter.check("1.2.3.4")
        with pytest.raises(ProblemException) as excinfo:
            limiter.check("1.2.3.4")
        assert excinfo.value.status_code == 429

    def test_clients_are_independent(self):
        limiter = SubmissionRateLimiter(1)
        limiter.check("1.1.1.1")
        limiter.check("2.2.2.2")  # different client unaffected


class TestCustomAreaLimits:
    """Drawn areas are capped far tighter than predefined regions.

    Predefined regions are curated and run at ~84-137 km²; arbitrary public
    submissions are bounded to a few km² so processing stays cheap. Conflating
    the two limits would either break every region or remove the cost control.
    """

    def test_custom_limit_defaults_to_two_km2(self):
        assert make_settings().effective_max_custom_aoi_area_km2() == 2.0

    def test_custom_limit_is_far_below_the_region_limit(self):
        settings = make_settings()
        assert settings.effective_max_custom_aoi_area_km2() < settings.max_aoi_area_km2

    def test_custom_limit_never_exceeds_the_global_ceiling(self):
        settings = make_settings(max_aoi_area_km2=1.0, max_custom_aoi_area_km2=50.0)
        assert settings.effective_max_custom_aoi_area_km2() == 1.0

    def test_custom_limit_is_configurable(self):
        settings = make_settings(max_custom_aoi_area_km2=25.0)
        assert settings.effective_max_custom_aoi_area_km2() == 25.0

    def test_custom_areas_enabled_by_default_even_in_demo_mode(self):
        assert make_settings(demo_mode=True).allow_custom_areas is True

    def test_custom_areas_can_be_switched_off(self):
        assert make_settings(allow_custom_areas=False).allow_custom_areas is False
