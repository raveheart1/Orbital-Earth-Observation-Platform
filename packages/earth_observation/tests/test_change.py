"""Per-pixel change maps: known deltas, valid-in-both masking, statistics."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from rasterio.transform import from_origin

from earth_observation.acquisition import group_acquisitions
from earth_observation.change import compute_change
from earth_observation.cog import read_ndvi_array, validate_cog, write_ndvi_cog
from earth_observation.grid import CanonicalGrid
from earth_observation.processing import process_acquisition
from earth_observation.testing import (
    NODATA_DN,
    ORIGIN_X,
    ORIGIN_Y,
    RES,
    SIZE,
    build_synthetic_scene,
    make_file_candidate,
    write_raster,
)
from earth_observation.types import ProcessingConfig


def test_known_deltas_including_negative():
    earlier = np.array([[0.2, 0.5, 0.8], [0.4, 0.1, 0.6]], dtype=np.float32)
    later = np.array([[0.5, 0.3, 0.8], [0.1, 0.4, 0.2]], dtype=np.float32)
    aoi = np.ones((2, 3), dtype=bool)
    delta, stats = compute_change(earlier, later, aoi, delta_threshold=0.1)
    np.testing.assert_allclose(delta, [[0.3, -0.2, 0.0], [-0.3, 0.3, -0.4]], atol=1e-6)
    values = [0.3, -0.2, 0.0, -0.3, 0.3, -0.4]
    assert stats.aoi_pixel_count == 6
    assert stats.valid_both_pixel_count == 6
    assert stats.valid_both_pct == pytest.approx(100.0)
    assert stats.delta_mean == pytest.approx(np.mean(values), abs=1e-6)
    assert stats.delta_median == pytest.approx(np.median(values), abs=1e-6)
    assert stats.delta_std == pytest.approx(np.std(values), abs=1e-6)
    assert stats.delta_p10 == pytest.approx(np.percentile(values, 10), abs=1e-6)
    assert stats.delta_p90 == pytest.approx(np.percentile(values, 90), abs=1e-6)
    assert stats.pct_increased == pytest.approx(100.0 * 2 / 6, abs=1e-3)
    assert stats.pct_decreased == pytest.approx(100.0 * 3 / 6, abs=1e-3)


def test_valid_in_one_only_is_nodata():
    earlier = np.array([[0.5, np.nan, 0.5, 0.5]], dtype=np.float32)
    later = np.array([[0.7, 0.7, np.nan, 0.7]], dtype=np.float32)
    aoi = np.array([[True, True, True, False]])
    delta, stats = compute_change(earlier, later, aoi, delta_threshold=0.1)
    assert delta[0, 0] == pytest.approx(0.2, abs=1e-6)
    assert np.isnan(delta[0, 1])  # valid only in later
    assert np.isnan(delta[0, 2])  # valid only in earlier
    assert np.isnan(delta[0, 3])  # outside the AOI, however clean the inputs
    assert stats.aoi_pixel_count == 3
    assert stats.valid_both_pixel_count == 1
    assert stats.valid_both_pct == pytest.approx(100.0 / 3, abs=1e-3)


def test_increased_decreased_fractions():
    # 10 valid pixels: 2 above +0.1, 3 below -0.1, 5 within the noise band.
    earlier = np.zeros((1, 10), dtype=np.float32)
    later = np.array(
        [[0.2, 0.15, -0.2, -0.15, -0.12, 0.08, -0.08, 0.05, 0.0, -0.05]], dtype=np.float32
    )
    aoi = np.ones((1, 10), dtype=bool)
    _, stats = compute_change(earlier, later, aoi, delta_threshold=0.1)
    assert stats.pct_increased == pytest.approx(20.0)
    assert stats.pct_decreased == pytest.approx(30.0)


def test_no_comparable_pixels():
    earlier = np.full((2, 2), np.nan, dtype=np.float32)
    later = np.full((2, 2), 0.5, dtype=np.float32)
    aoi = np.ones((2, 2), dtype=bool)
    delta, stats = compute_change(earlier, later, aoi, delta_threshold=0.1)
    assert np.isnan(delta).all()
    assert stats.valid_both_pixel_count == 0
    assert stats.valid_both_pct == 0.0
    assert stats.delta_mean is None
    assert stats.pct_increased is None
    assert stats.pct_decreased is None


def test_shape_and_threshold_validation():
    ok = np.zeros((2, 2), dtype=np.float32)
    mask = np.ones((2, 2), dtype=bool)
    with pytest.raises(ValueError, match="shapes differ"):
        compute_change(ok, np.zeros((3, 3), dtype=np.float32), mask, delta_threshold=0.1)
    with pytest.raises(ValueError, match="AOI mask"):
        compute_change(ok, ok, np.ones((3, 3), dtype=bool), delta_threshold=0.1)
    with pytest.raises(ValueError, match="delta_threshold"):
        compute_change(ok, ok, mask, delta_threshold=0.0)


def test_change_cog_roundtrips_and_validates(tmp_path):
    delta = np.random.default_rng(7).uniform(-0.6, 0.6, size=(64, 64)).astype(np.float32)
    delta[5:9, 5:9] = np.nan
    path = tmp_path / "ndvi_change.tif"
    write_ndvi_cog(
        path,
        delta,
        transform=from_origin(300_000.0, 4_700_000.0, 10.0, 10.0),
        crs="EPSG:32617",
        nodata=-9999.0,
    )
    is_valid, errors, _ = validate_cog(path)
    assert is_valid, errors
    restored = read_ndvi_array(path)
    assert np.isnan(restored[5:9, 5:9]).all()
    valid = np.isfinite(delta)
    np.testing.assert_array_equal(restored[valid], delta[valid])


def test_change_between_two_processed_observations(tmp_path):
    """The worker-level flow: process two acquisitions onto ONE canonical
    grid, re-read their NDVI COGs, and difference them."""
    scene_a = build_synthetic_scene(tmp_path / "scene_a")  # background NDVI 0.5
    scene_b_dir = tmp_path / "scene_b"
    scene_b_dir.mkdir()
    # Uniform NDVI 0.2: red refl 0.2 (DN 3000), NIR refl 0.3 (DN 4000).
    write_raster(
        scene_b_dir / "red.tif",
        np.full((SIZE, SIZE), 3000, dtype=np.uint16),
        nodata=NODATA_DN,
    )
    write_raster(
        scene_b_dir / "nir.tif",
        np.full((SIZE, SIZE), 4000, dtype=np.uint16),
        nodata=NODATA_DN,
    )
    write_raster(
        scene_b_dir / "scl.tif",
        np.full((SIZE // 2, SIZE // 2), 4, dtype=np.uint8),
        transform=from_origin(ORIGIN_X, ORIGIN_Y, RES * 2, RES * 2),
        nodata=0,
    )
    candidate_b = make_file_candidate(scene_b_dir, item_id="S2_TEST_SCENE_B", with_visual=False)

    aoi = scene_a["aoi_geojson"]
    grid = CanonicalGrid.from_aoi(aoi, resolution_m=10.0)
    config = ProcessingConfig(min_valid_pixel_pct=10.0, preview_max_dim=256)
    result_a = process_acquisition(
        group_acquisitions([scene_a["candidate"]], aoi)[0], grid, config, tmp_path / "a", sign=str
    )
    result_b = process_acquisition(
        group_acquisitions([candidate_b], aoi)[0], grid, config, tmp_path / "b", sign=str
    )
    assert result_a.usable and result_b.usable

    delta, stats = compute_change(
        read_ndvi_array(Path(result_a.outputs.ndvi_cog)),
        read_ndvi_array(Path(result_b.outputs.ndvi_cog)),
        grid.aoi_mask(),
        delta_threshold=config.change_delta_threshold,
    )
    # Background 0.5 -> 0.2; the swapped block in A went -0.5 -> 0.2 (+0.7).
    assert stats.delta_median == pytest.approx(-0.3, abs=2e-3)
    assert float(np.nanmax(delta)) == pytest.approx(0.7, abs=2e-3)
    # Scene B is fully valid, so valid-in-both is exactly A's valid set: the
    # cloud-bait, nodata, and zero-denominator pixels of A have no change.
    assert stats.valid_both_pixel_count == result_a.stats.valid_pixel_count
    assert stats.aoi_pixel_count == grid.aoi_pixel_count()
    increased = 100.0 * 16 / stats.valid_both_pixel_count  # the 4x4 swapped block
    assert stats.pct_increased == pytest.approx(increased, abs=1e-3)
    assert stats.pct_increased + stats.pct_decreased == pytest.approx(100.0, abs=1e-3)
