"""Unit tests for NDVI math, reflectance scaling, and invalid-pixel handling."""

from __future__ import annotations

import numpy as np
import pytest

from earth_observation.ndvi import compute_ndvi, resolve_band_scaling, to_reflectance
from earth_observation.types import BandScaling


class TestComputeNdvi:
    def test_known_values(self):
        red = np.array([[0.1, 0.2]], dtype=np.float64)
        nir = np.array([[0.3, 0.2]], dtype=np.float64)
        ndvi, zeros = compute_ndvi(red, nir)
        assert ndvi[0, 0] == pytest.approx(0.5, abs=1e-6)
        assert ndvi[0, 1] == pytest.approx(0.0, abs=1e-6)
        assert zeros == 0
        assert ndvi.dtype == np.float32

    def test_negative_ndvi(self):
        red = np.array([[0.3]], dtype=np.float64)
        nir = np.array([[0.1]], dtype=np.float64)
        ndvi, _ = compute_ndvi(red, nir)
        assert ndvi[0, 0] == pytest.approx(-0.5, abs=1e-6)

    def test_zero_denominator_is_nan_and_counted(self):
        red = np.array([[0.0, 0.1]], dtype=np.float64)
        nir = np.array([[0.0, 0.3]], dtype=np.float64)
        ndvi, zeros = compute_ndvi(red, nir)
        assert np.isnan(ndvi[0, 0])
        assert ndvi[0, 1] == pytest.approx(0.5, abs=1e-6)
        assert zeros == 1

    def test_negative_reflectance_clipped_keeps_ndvi_bounded(self):
        """Retrieval artifacts (refl < 0) must never produce |NDVI| > 1."""
        red = np.array([[-0.05, 0.2, 0.001]], dtype=np.float64)
        nir = np.array([[0.2, -0.1, -0.001]], dtype=np.float64)
        ndvi, zeros = compute_ndvi(red, nir)
        assert ndvi[0, 0] == pytest.approx(1.0)
        assert ndvi[0, 1] == pytest.approx(-1.0)
        assert ndvi[0, 2] == pytest.approx(-1.0)
        assert zeros == 0
        finite = ndvi[np.isfinite(ndvi)]
        assert (np.abs(finite) <= 1.0).all()

    def test_nodata_propagates_as_nan(self):
        red = np.array([[np.nan, 0.1]], dtype=np.float64)
        nir = np.array([[0.3, np.nan]], dtype=np.float64)
        ndvi, zeros = compute_ndvi(red, nir)
        assert np.isnan(ndvi).all()
        assert zeros == 0

    def test_mask_excludes_pixels(self):
        red = np.full((2, 2), 0.1)
        nir = np.full((2, 2), 0.3)
        mask = np.array([[True, False], [False, True]])
        ndvi, _ = compute_ndvi(red, nir, mask)
        assert ndvi[0, 0] == pytest.approx(0.5, abs=1e-6)
        assert np.isnan(ndvi[0, 1])
        assert np.isnan(ndvi[1, 0])

    def test_shape_mismatch_rejected(self):
        with pytest.raises(ValueError, match="shapes differ"):
            compute_ndvi(np.zeros((2, 2)), np.zeros((3, 3)))

    def test_mask_shape_mismatch_rejected(self):
        with pytest.raises(ValueError, match="Mask shape"):
            compute_ndvi(np.zeros((2, 2)), np.zeros((2, 2)), np.ones((3, 3), dtype=bool))

    def test_full_range_preserved(self):
        """NDVI must span [-1, 1]; no display clamping in analytical output."""
        red = np.array([[1.0, 0.0]], dtype=np.float64)
        nir = np.array([[0.0, 1.0]], dtype=np.float64)
        ndvi, _ = compute_ndvi(red, nir)
        assert ndvi[0, 0] == pytest.approx(-1.0)
        assert ndvi[0, 1] == pytest.approx(1.0)


class TestScaling:
    def test_baseline_4_offset(self):
        scaling = resolve_band_scaling(None, "05.00")
        assert scaling.offset == pytest.approx(-0.1)
        assert scaling.scale == pytest.approx(1e-4)
        assert scaling.source == "baseline_heuristic"

    def test_pre_baseline_4_no_offset(self):
        scaling = resolve_band_scaling(None, "03.01")
        assert scaling.offset == 0.0
        assert scaling.source == "baseline_heuristic"

    def test_raster_extension_takes_priority(self):
        scaling = resolve_band_scaling({"scale": 2e-4, "offset": -0.2}, "05.00")
        assert scaling.scale == pytest.approx(2e-4)
        assert scaling.offset == pytest.approx(-0.2)
        assert scaling.source == "raster_ext"

    def test_unknown_baseline_defaults(self):
        scaling = resolve_band_scaling(None, None)
        assert scaling.offset == 0.0
        assert scaling.source == "default"

    def test_offset_changes_ndvi(self):
        """The baseline-04 offset materially changes NDVI — the reason we model it."""
        dn_red = np.array([[3000.0]])
        dn_nir = np.array([[5000.0]])
        with_offset = BandScaling(scale=1e-4, offset=-0.1)
        without = BandScaling(scale=1e-4, offset=0.0)
        ndvi_correct, _ = compute_ndvi(
            to_reflectance(dn_red, with_offset), to_reflectance(dn_nir, with_offset)
        )
        ndvi_wrong, _ = compute_ndvi(
            to_reflectance(dn_red, without), to_reflectance(dn_nir, without)
        )
        assert ndvi_correct[0, 0] == pytest.approx((0.4 - 0.2) / (0.4 + 0.2), abs=1e-6)
        assert abs(ndvi_correct[0, 0] - ndvi_wrong[0, 0]) > 0.05
