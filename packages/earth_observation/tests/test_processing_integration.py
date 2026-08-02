"""End-to-end pipeline tests over tiny temporary GeoTIFFs.

These exercise the REAL processing code path (windowed reads, SCL
reproject-match from 20 m to 10 m, reflectance offset, masking, exact-AOI
clipping, COG/preview/summary outputs) — only the data is synthetic and the
Planetary Computer URL signer is replaced with the identity function.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from earth_observation.cog import validate_cog
from earth_observation.processing import process_scene
from earth_observation.testing import (
    NODATA_DN,
    ORIGIN_X,
    ORIGIN_Y,
    RES,
    SIZE,
    utm_box_to_wgs84_geojson,
    write_raster,
)
from earth_observation.testing import (
    make_file_candidate as make_candidate,
)
from earth_observation.timeseries import analysis_summary, write_timeseries_csv
from earth_observation.types import ProcessingConfig

IDENTITY = str  # "signing" for local files is the identity function

CONFIG = ProcessingConfig(min_valid_pixel_pct=10.0, preview_max_dim=256)


@pytest.fixture
def result(synthetic_scene, tmp_path):
    out = tmp_path / "out"
    return process_scene(
        synthetic_scene["candidate"],
        synthetic_scene["aoi_geojson"],
        CONFIG,
        out,
        sign=IDENTITY,
    )


class TestFullPipeline:
    def test_scene_usable_with_expected_counts(self, result):
        assert result.usable
        stats = result.stats
        # AOI is 20x20 pixels = 400; projection round-trip can shift edges by
        # at most one pixel per edge.
        assert 360 <= stats.aoi_pixel_count <= 440
        # Invalid inside AOI: 8 cloud + 4 nodata + 2 zero-denominator = 14.
        assert stats.masked_pixel_count >= 14
        assert stats.valid_pixel_count == stats.aoi_pixel_count - stats.masked_pixel_count
        assert stats.zero_denominator_pixel_count == 2

    def test_ndvi_values_scientifically_correct(self, result):
        stats = result.stats
        # Background NDVI 0.5, negative block -0.5 (16 px).
        assert stats.ndvi_max == pytest.approx(0.5, abs=1e-4)
        assert stats.ndvi_min == pytest.approx(-0.5, abs=1e-4)
        assert stats.ndvi_median == pytest.approx(0.5, abs=1e-4)
        # Cloud-covered pixels carried NDVI ~0.9 bait values; masking must keep
        # the maximum at 0.5.
        assert stats.ndvi_max < 0.55

    def test_reflectance_offset_applied(self, result):
        assert result.scaling is not None
        assert result.scaling.offset == pytest.approx(-0.1)
        assert result.scaling.source == "baseline_heuristic"

    def test_cog_output_valid_and_clipped_to_aoi(self, result):
        is_valid, errors, _ = validate_cog(result.outputs.ndvi_cog)
        assert is_valid, errors
        with rasterio.open(result.outputs.ndvi_cog) as src:
            assert src.crs.to_epsg() == 32617
            data = src.read(1)
            # Output covers the AOI window (+pad), far smaller than the scene.
            assert data.shape[0] < SIZE and data.shape[1] < SIZE
            # Corner pixels (outside the AOI polygon) are nodata.
            assert data[0, 0] == CONFIG.output_nodata

    def test_previews_and_summary_written(self, result):
        outputs = result.outputs
        assert outputs.ndvi_preview.endswith(".png")
        assert outputs.true_color_preview is not None
        summary = json.loads(open(outputs.scene_summary).read())
        assert summary["usable"] is True
        assert summary["stats"]["valid_pixel_count"] == result.stats.valid_pixel_count
        assert summary["mask_policy_scl_classes"] == list(CONFIG.masked_scl_classes)
        # Provenance-critical: original (unsigned) asset refs recorded.
        assert summary["source_assets_unsigned"]["red"].endswith("red.tif")

    def test_timeseries_and_analysis_summary(self, result, tmp_path):
        csv_path = tmp_path / "timeseries.csv"
        count = write_timeseries_csv(csv_path, [result])
        assert count == 1
        content = csv_path.read_text()
        assert "ndvi_mean" in content.splitlines()[0]
        summary = analysis_summary([result])
        assert summary["usable_scene_count"] == 1
        assert summary["ndvi_mean_change"] == pytest.approx(0.0)


class TestDegenerateScenes:
    def test_fully_clouded_scene_unusable(self, tmp_path, synthetic_scene):
        scene_dir = synthetic_scene["dir"]
        scl_cloudy = np.full((SIZE // 2, SIZE // 2), 9, dtype=np.uint8)
        write_raster(
            scene_dir / "scl.tif",
            scl_cloudy,
            transform=from_origin(ORIGIN_X, ORIGIN_Y, RES * 2, RES * 2),
            nodata=0,
        )
        result = process_scene(
            synthetic_scene["candidate"],
            synthetic_scene["aoi_geojson"],
            CONFIG,
            tmp_path / "out2",
            sign=IDENTITY,
        )
        assert not result.usable
        assert result.unusable_reason == "all_pixels_masked"
        assert result.stats.valid_pixel_count == 0

    def test_insufficient_valid_pixels(self, tmp_path, synthetic_scene):
        scene_dir = synthetic_scene["dir"]
        scl = np.full((SIZE // 2, SIZE // 2), 9, dtype=np.uint8)
        scl[5, 5] = 4  # one clear 20 m cell -> 4 valid 10 m pixels ~ 1%
        write_raster(
            scene_dir / "scl.tif",
            scl,
            transform=from_origin(ORIGIN_X, ORIGIN_Y, RES * 2, RES * 2),
            nodata=0,
        )
        result = process_scene(
            synthetic_scene["candidate"],
            synthetic_scene["aoi_geojson"],
            CONFIG,
            tmp_path / "out3",
            sign=IDENTITY,
        )
        assert not result.usable
        assert result.unusable_reason == "insufficient_valid_pixels"
        assert 0 < result.stats.valid_pixel_pct < CONFIG.min_valid_pixel_pct

    def test_aoi_outside_scene(self, tmp_path, synthetic_scene):
        far_away = utm_box_to_wgs84_geojson(
            ORIGIN_X + 100_000, ORIGIN_Y + 100_000, ORIGIN_X + 100_500, ORIGIN_Y + 100_500
        )
        result = process_scene(
            synthetic_scene["candidate"],
            far_away,
            CONFIG,
            tmp_path / "out4",
            sign=IDENTITY,
        )
        assert not result.usable
        assert result.unusable_reason == "no_raster_overlap_with_aoi"

    def test_misaligned_nir_reprojected(self, tmp_path, synthetic_scene):
        """NIR shipped at 20 m on a shifted grid must be aligned, not crash."""
        scene_dir = synthetic_scene["dir"]
        nir_20m = np.full((SIZE // 2, SIZE // 2), 4000, dtype=np.uint16)
        write_raster(
            scene_dir / "nir.tif",
            nir_20m,
            transform=from_origin(ORIGIN_X, ORIGIN_Y, RES * 2, RES * 2),
            nodata=NODATA_DN,
        )
        result = process_scene(
            synthetic_scene["candidate"],
            synthetic_scene["aoi_geojson"],
            CONFIG,
            tmp_path / "out5",
            sign=IDENTITY,
        )
        assert result.usable
        assert any("reprojected" in w for w in result.warnings)
        # Background NDVI still 0.5 after alignment.
        assert result.stats.ndvi_median == pytest.approx(0.5, abs=1e-3)

    def test_scene_without_visual_asset(self, tmp_path, synthetic_scene):
        candidate = make_candidate(synthetic_scene["dir"], with_visual=False)
        result = process_scene(
            candidate,
            synthetic_scene["aoi_geojson"],
            CONFIG,
            tmp_path / "out6",
            sign=IDENTITY,
        )
        assert result.usable
        assert result.outputs.true_color_preview is None
        assert any("visual" in w for w in result.warnings)
