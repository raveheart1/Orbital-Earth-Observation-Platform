"""COG writing and structural validation tests."""

from __future__ import annotations

import numpy as np
import rasterio
from rasterio.transform import from_origin

from earth_observation.cog import read_raster_info, validate_cog, write_ndvi_cog


def test_written_cog_is_valid_and_roundtrips(tmp_path):
    ndvi = np.random.default_rng(1).uniform(-1, 1, size=(64, 64)).astype(np.float32)
    ndvi[10:14, 10:14] = np.nan
    path = tmp_path / "ndvi.tif"
    transform = from_origin(300_000.0, 4_700_000.0, 10.0, 10.0)
    write_ndvi_cog(path, ndvi, transform=transform, crs="EPSG:32617", nodata=-9999.0)

    is_valid, errors, _ = validate_cog(path)
    assert is_valid, f"COG validation failed: {errors}"

    with rasterio.open(path) as src:
        assert src.nodata == -9999.0
        assert src.dtypes[0] == "float32"
        assert src.crs.to_epsg() == 32617
        data = src.read(1)
    # NaN cells were written as the explicit nodata value.
    assert (data[10:14, 10:14] == -9999.0).all()
    # Valid cells survive exactly (float32 -> float32).
    valid = np.isfinite(ndvi)
    np.testing.assert_array_equal(data[valid], ndvi[valid])


def test_raster_info(tmp_path):
    ndvi = np.zeros((8, 8), dtype=np.float32)
    path = tmp_path / "n.tif"
    write_ndvi_cog(
        path,
        ndvi,
        transform=from_origin(0, 80, 10.0, 10.0),
        crs="EPSG:32617",
        nodata=-9999.0,
    )
    info = read_raster_info(path)
    assert info["width"] == 8
    assert info["resolution"] == (10.0, 10.0)
    assert info["crs"] == "EPSG:32617"
    assert info["nodata"] == -9999.0
