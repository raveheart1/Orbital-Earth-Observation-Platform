"""Settings and demo-mode limit tests."""

from __future__ import annotations

from oeop_core.settings import Settings


def make_settings(**overrides) -> Settings:
    # _env_file=None keeps developer .env files out of unit tests.
    return Settings(_env_file=None, **overrides)


def test_defaults_are_conservative():
    s = make_settings()
    assert s.max_aoi_area_km2 <= 1000
    assert s.max_scene_limit <= 20
    assert s.max_dequeue_count >= 2
    assert s.per_analysis_storage_limit_mb <= 500
    assert s.output_retention_days <= 90
    assert s.submissions_enabled is True


def test_demo_mode_tightens_limits():
    s = make_settings(demo_mode=True)
    assert s.effective_max_aoi_area_km2() == s.demo_max_aoi_area_km2
    assert s.effective_max_scene_limit() == s.demo_max_scene_limit
    assert s.effective_max_date_span_days() == s.demo_max_date_span_days


def test_normal_mode_uses_full_limits():
    s = make_settings(demo_mode=False)
    assert s.effective_max_aoi_area_km2() == s.max_aoi_area_km2


def test_cors_origins_parsing():
    s = make_settings(cors_allowed_origins="https://a.example, https://b.example")
    assert s.cors_origins == ["https://a.example", "https://b.example"]


def test_env_prefix(monkeypatch):
    monkeypatch.setenv("OEOP_MAX_AOI_AREA_KM2", "123.5")
    s = Settings(_env_file=None)
    assert s.max_aoi_area_km2 == 123.5
