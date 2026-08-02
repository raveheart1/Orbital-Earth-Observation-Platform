"""Statistics must be computed exclusively from valid pixels inside the AOI."""

from __future__ import annotations

import numpy as np
import pytest

from earth_observation.stats import compute_scene_stats


def test_known_statistics():
    ndvi = np.array([[0.2, 0.4, np.nan], [0.6, 0.8, np.nan]], dtype=np.float32)
    aoi = np.array([[True, True, True], [True, True, False]])
    stats = compute_scene_stats(ndvi, aoi, zero_denominator_count=1)
    assert stats.aoi_pixel_count == 5
    assert stats.valid_pixel_count == 4
    assert stats.masked_pixel_count == 1
    assert stats.valid_pixel_pct == pytest.approx(80.0)
    assert stats.ndvi_mean == pytest.approx(0.5, abs=1e-6)
    assert stats.ndvi_median == pytest.approx(0.5, abs=1e-6)
    assert stats.ndvi_min == pytest.approx(0.2, abs=1e-6)
    assert stats.ndvi_max == pytest.approx(0.8, abs=1e-6)
    assert stats.ndvi_std == pytest.approx(np.std([0.2, 0.4, 0.6, 0.8]), abs=1e-6)
    assert stats.zero_denominator_pixel_count == 1


def test_percentiles():
    values = np.linspace(0.0, 1.0, 101, dtype=np.float32).reshape(1, -1)
    aoi = np.ones_like(values, dtype=bool)
    stats = compute_scene_stats(values, aoi, 0)
    assert stats.ndvi_p10 == pytest.approx(0.1, abs=1e-6)
    assert stats.ndvi_p25 == pytest.approx(0.25, abs=1e-6)
    assert stats.ndvi_p75 == pytest.approx(0.75, abs=1e-6)
    assert stats.ndvi_p90 == pytest.approx(0.9, abs=1e-6)


def test_pixels_outside_aoi_never_contribute():
    ndvi = np.array([[0.5, 99.0]], dtype=np.float32)  # 99 outside AOI
    aoi = np.array([[True, False]])
    stats = compute_scene_stats(ndvi, aoi, 0)
    assert stats.ndvi_max == pytest.approx(0.5, abs=1e-6)
    assert stats.aoi_pixel_count == 1


def test_fully_masked_scene():
    ndvi = np.full((3, 3), np.nan, dtype=np.float32)
    aoi = np.ones((3, 3), dtype=bool)
    stats = compute_scene_stats(ndvi, aoi, 0)
    assert stats.valid_pixel_count == 0
    assert stats.valid_pixel_pct == 0.0
    assert stats.ndvi_mean is None
    assert stats.ndvi_min is None


def test_empty_aoi():
    ndvi = np.full((2, 2), 0.5, dtype=np.float32)
    aoi = np.zeros((2, 2), dtype=bool)
    stats = compute_scene_stats(ndvi, aoi, 0)
    assert stats.aoi_pixel_count == 0
    assert stats.valid_pixel_pct == 0.0


def test_shape_mismatch_rejected():
    with pytest.raises(ValueError, match="does not match"):
        compute_scene_stats(np.zeros((2, 2)), np.ones((3, 3), dtype=bool), 0)
