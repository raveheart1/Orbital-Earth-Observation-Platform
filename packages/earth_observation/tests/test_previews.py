"""Preview rendering tests."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from earth_observation.previews import (
    change_colormap_lut,
    change_legend_spec,
    legend_spec,
    ndvi_colormap_lut,
    write_change_preview,
    write_ndvi_preview,
    write_true_color_preview,
)


def test_ndvi_preview_transparent_where_invalid(tmp_path):
    ndvi = np.full((10, 10), 0.6, dtype=np.float32)
    ndvi[0, 0] = np.nan
    path = tmp_path / "p.png"
    write_ndvi_preview(path, ndvi, display_min=-0.2, display_max=0.9)
    with Image.open(path) as img:
        assert img.mode == "RGBA"
        alpha = np.asarray(img)[:, :, 3]
    assert alpha[0, 0] == 0
    assert alpha[1, 1] == 255


def test_high_ndvi_is_greener_than_low(tmp_path):
    lut = ndvi_colormap_lut()
    low, high = lut[30], lut[240]
    assert high[1] > high[0]  # green dominates at high NDVI
    assert low[0] > low[1] or low[2] < 100  # brownish at low NDVI


def test_preview_downsampled_to_max_dim(tmp_path):
    ndvi = np.zeros((3000, 1000), dtype=np.float32)
    path = tmp_path / "p.png"
    write_ndvi_preview(path, ndvi, display_min=-0.2, display_max=0.9, max_dim=512)
    with Image.open(path) as img:
        assert max(img.size) <= 512


def test_invalid_display_range_rejected(tmp_path):
    with pytest.raises(ValueError, match="display_max"):
        write_ndvi_preview(
            tmp_path / "p.png",
            np.zeros((4, 4), dtype=np.float32),
            display_min=0.5,
            display_max=0.5,
        )


def test_true_color_preview(tmp_path):
    rgb = np.random.default_rng(3).integers(0, 255, size=(20, 30, 3), dtype=np.uint8)
    mask = np.ones((20, 30), dtype=bool)
    mask[0, :] = False
    path = tmp_path / "tc.png"
    write_true_color_preview(path, rgb, valid_mask=mask)
    with Image.open(path) as img:
        arr = np.asarray(img)
    assert arr.shape == (20, 30, 4)
    assert (arr[0, :, 3] == 0).all()


def test_true_color_shape_validation(tmp_path):
    with pytest.raises(ValueError, match="RGB"):
        write_true_color_preview(tmp_path / "x.png", np.zeros((4, 4), dtype=np.uint8))


def test_legend_spec_matches_display_range():
    spec = legend_spec(-0.2, 0.9)
    assert spec["display_min"] == -0.2
    assert spec["stops"][0]["value"] == -0.2  # type: ignore[index]
    assert spec["stops"][-1]["value"] == 0.9  # type: ignore[index]


def test_change_preview_center_zero_and_transparent_invalid(tmp_path):
    delta = np.zeros((10, 10), dtype=np.float32)
    delta[0, 0] = np.nan
    path = tmp_path / "c.png"
    write_change_preview(path, delta, display_range=0.4)
    with Image.open(path) as img:
        arr = np.asarray(img)
    assert arr[0, 0, 3] == 0  # no defined change -> transparent
    assert arr[5, 5, 3] == 255
    # Zero change renders the near-white center of the diverging ramp.
    assert (arr[5, 5, :3].astype(int) >= 235).all()


def test_change_ramp_is_diverging():
    lut = change_colormap_lut()
    low, mid, high = lut[10], lut[128], lut[245]
    assert (mid.astype(int) >= 230).all()  # near-white center
    assert low[0] > low[2]  # brown at strong loss
    assert high[1] > high[0]  # green at strong gain


def test_change_display_range_symmetric_and_clipped(tmp_path):
    delta = np.array([[-0.4, 0.4], [-1.0, 1.0]], dtype=np.float32)
    path = tmp_path / "c.png"
    write_change_preview(path, delta, display_range=0.4)
    with Image.open(path) as img:
        arr = np.asarray(img)
    # Values beyond the fixed range clip to the same ramp ends.
    np.testing.assert_array_equal(arr[0, 0], arr[1, 0])
    np.testing.assert_array_equal(arr[0, 1], arr[1, 1])


def test_change_invalid_display_range_rejected(tmp_path):
    with pytest.raises(ValueError, match="display_range"):
        write_change_preview(
            tmp_path / "c.png",
            np.zeros((4, 4), dtype=np.float32),
            display_range=0.0,
        )


def test_change_legend_spec_symmetric_around_zero():
    spec = change_legend_spec(0.4)
    assert spec["type"] == "ndvi_change"
    assert spec["display_min"] == -0.4
    assert spec["display_max"] == 0.4
    assert spec["stops"][0]["value"] == -0.4  # type: ignore[index]
    assert spec["stops"][3]["value"] == 0.0  # type: ignore[index]
    assert spec["stops"][-1]["value"] == 0.4  # type: ignore[index]
