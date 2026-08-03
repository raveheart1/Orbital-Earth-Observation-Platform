"""End-to-end pipeline tests over tiny temporary GeoTIFFs.

These exercise the REAL processing code path (windowed reads, mosaicking onto
the canonical grid, SCL nearest-neighbour alignment, reflectance offset,
masking, exact-AOI statistics, COG/preview/summary outputs) — only the data is
synthetic and the Planetary Computer URL signer is the identity function.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from earth_observation.acquisition import group_acquisitions
from earth_observation.cog import validate_cog
from earth_observation.grid import CanonicalGrid
from earth_observation.processing import process_acquisition
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


def acquisition_for(scene: dict):
    return group_acquisitions([scene["candidate"]], scene["aoi_geojson"])[0]


def grid_for(scene: dict) -> CanonicalGrid:
    return CanonicalGrid.from_aoi(scene["aoi_geojson"], resolution_m=10.0)


@pytest.fixture
def result(synthetic_scene, tmp_path):
    return process_acquisition(
        acquisition_for(synthetic_scene),
        grid_for(synthetic_scene),
        CONFIG,
        tmp_path / "out",
        sign=IDENTITY,
    )


class TestFullPipeline:
    def test_scene_usable_with_expected_counts(self, result, synthetic_scene):
        assert result.usable, result.unusable_reason
        stats = result.stats
        grid = grid_for(synthetic_scene)
        # The AOI footprint comes from the canonical grid, not the source extent.
        assert stats.aoi_pixel_count == grid.aoi_pixel_count()
        assert stats.valid_pixel_count == stats.aoi_pixel_count - stats.masked_pixel_count
        assert stats.masked_pixel_count >= 14  # cloud + nodata + zero-denominator

    def test_ndvi_values_scientifically_correct(self, result):
        stats = result.stats
        # Background NDVI 0.5, negative block -0.5.
        assert stats.ndvi_max == pytest.approx(0.5, abs=1e-3)
        assert stats.ndvi_min == pytest.approx(-0.5, abs=1e-3)
        assert stats.ndvi_median == pytest.approx(0.5, abs=1e-3)
        # Cloud-covered pixels carried NDVI ~0.9 bait values; masking must hold.
        assert stats.ndvi_max < 0.55

    def test_reflectance_offset_applied(self, result):
        assert result.scaling is not None
        assert result.scaling.offset == pytest.approx(-0.1)
        assert result.scaling.source == "baseline_heuristic"

    def test_cog_matches_the_canonical_grid(self, result, synthetic_scene):
        grid = grid_for(synthetic_scene)
        is_valid, errors, _ = validate_cog(result.outputs.ndvi_cog)
        assert is_valid, errors
        with rasterio.open(result.outputs.ndvi_cog) as src:
            assert src.crs.to_string() == grid.crs
            assert (src.width, src.height) == (grid.width, grid.height)
            assert src.transform == grid.transform

    def test_previews_and_summary_written(self, result):
        outputs = result.outputs
        assert outputs.ndvi_preview.endswith(".png")
        assert outputs.true_color_preview is not None
        summary = json.loads(open(outputs.scene_summary).read())
        assert summary["usable"] is True
        assert summary["stats"]["valid_pixel_count"] == result.stats.valid_pixel_count
        assert summary["mask_policy_scl_classes"] == list(CONFIG.masked_scl_classes)
        assert summary["canonical_grid"]["signature"]
        # Provenance-critical: original (unsigned) asset refs recorded per granule.
        item_id = result.acquisition.primary_item_id
        assert summary["source_assets_unsigned"][item_id]["red"].endswith("red.tif")

    def test_coverage_recorded(self, result):
        coverage = result.coverage
        assert coverage is not None
        assert coverage.aoi_coverage_pct > 99.0
        assert coverage.granule_count == 1
        assert coverage.contributing_item_ids

    def test_timeseries_and_analysis_summary(self, result, tmp_path):
        csv_path = tmp_path / "timeseries.csv"
        count = write_timeseries_csv(csv_path, [result])
        assert count == 1
        header = csv_path.read_text().splitlines()[0]
        assert "ndvi_mean" in header
        assert "aoi_coverage_pct" in header
        assert "contributing_item_ids" in header
        summary = analysis_summary([result])
        assert summary["usable_scene_count"] == 1
        assert summary["ndvi_mean_change"] == pytest.approx(0.0)
        assert summary["identical_analytical_grid"] is True


class TestDegenerateScenes:
    def test_fully_clouded_scene_unusable(self, tmp_path, synthetic_scene):
        write_raster(
            synthetic_scene["dir"] / "scl.tif",
            np.full((SIZE // 2, SIZE // 2), 9, dtype=np.uint8),
            transform=from_origin(ORIGIN_X, ORIGIN_Y, RES * 2, RES * 2),
            nodata=0,
        )
        result = process_acquisition(
            acquisition_for(synthetic_scene),
            grid_for(synthetic_scene),
            CONFIG,
            tmp_path / "out2",
            sign=IDENTITY,
        )
        assert not result.usable
        assert result.unusable_reason == "all_pixels_masked"
        assert result.stats.valid_pixel_count == 0
        assert result.coverage.cloud_masked_pixel_count > 0

    def test_insufficient_valid_pixels(self, tmp_path, synthetic_scene):
        scl = np.full((SIZE // 2, SIZE // 2), 9, dtype=np.uint8)
        scl[5, 5] = 4  # one clear 20 m cell ~ 1% of the AOI
        write_raster(
            synthetic_scene["dir"] / "scl.tif",
            scl,
            transform=from_origin(ORIGIN_X, ORIGIN_Y, RES * 2, RES * 2),
            nodata=0,
        )
        result = process_acquisition(
            acquisition_for(synthetic_scene),
            grid_for(synthetic_scene),
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
        acquisition = group_acquisitions([synthetic_scene["candidate"]], far_away)[0]
        result = process_acquisition(
            acquisition,
            CanonicalGrid.from_aoi(far_away, resolution_m=10.0),
            CONFIG,
            tmp_path / "out4",
            sign=IDENTITY,
        )
        assert not result.usable
        assert result.unusable_reason == "no_raster_overlap_with_aoi"

    def test_misaligned_nir_reprojected_onto_the_grid(self, tmp_path, synthetic_scene):
        """NIR shipped at 20 m on a shifted grid must be aligned, not crash."""
        write_raster(
            synthetic_scene["dir"] / "nir.tif",
            np.full((SIZE // 2, SIZE // 2), 4000, dtype=np.uint16),
            transform=from_origin(ORIGIN_X, ORIGIN_Y, RES * 2, RES * 2),
            nodata=NODATA_DN,
        )
        grid = grid_for(synthetic_scene)
        result = process_acquisition(
            acquisition_for(synthetic_scene), grid, CONFIG, tmp_path / "out5", sign=IDENTITY
        )
        assert result.usable
        assert (result.raster.width, result.raster.height) == (grid.width, grid.height)
        assert result.stats.ndvi_median == pytest.approx(0.5, abs=1e-2)

    def test_scene_without_visual_asset(self, tmp_path, synthetic_scene):
        candidate = make_candidate(synthetic_scene["dir"], with_visual=False)
        acquisition = group_acquisitions([candidate], synthetic_scene["aoi_geojson"])[0]
        result = process_acquisition(
            acquisition,
            grid_for(synthetic_scene),
            CONFIG,
            tmp_path / "out6",
            sign=IDENTITY,
        )
        assert result.usable
        assert result.outputs.true_color_preview is None
        assert any("True-color" in w for w in result.warnings)
