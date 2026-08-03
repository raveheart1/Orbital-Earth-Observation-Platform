"""Regression tests for the spatial-comparability defect.

The production defect: an AOI straddling the T17TLG/T17TLH Sentinel-2 tile
boundary was processed from ONE granule per date, so dates backed by different
tiles produced rasters of different sizes covering different ground, and NDVI
statistics were computed over different geographic regions.

These tests use synthetic ADJACENT granules (no network) and assert the
properties that make observations comparable.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
import rasterio
from PIL import Image
from shapely.geometry import shape

from earth_observation.acquisition import (
    acquisition_key,
    group_acquisitions,
    parse_relative_orbit,
    parse_tile_id,
)
from earth_observation.grid import CanonicalGrid
from earth_observation.mosaic import mosaic_band
from earth_observation.processing import (
    UNUSABLE_INSUFFICIENT_COVERAGE,
    process_acquisition,
)
from earth_observation.selection import REASON_COVERAGE, select_acquisitions
from earth_observation.testing import build_adjacent_granules
from earth_observation.types import ProcessingConfig

IDENTITY = str  # local files need no signing

CONFIG = ProcessingConfig(preview_max_dim=256)


@pytest.fixture
def seam(tmp_path):
    """One acquisition, two adjacent granules, AOI spanning the seam."""
    return build_adjacent_granules(tmp_path / "granules")


@pytest.fixture
def seam_grid(seam):
    return CanonicalGrid.from_aoi(seam["aoi_geojson"], resolution_m=10.0)


class TestAcquisitionGrouping:
    def test_adjacent_granules_group_into_one_acquisition(self, seam):
        acqs = group_acquisitions(seam["candidates"], seam["aoi_geojson"])
        assert len(acqs) == 1
        assert acqs[0].granule_count == 2
        assert sorted(acqs[0].tile_ids) == ["T17TLG", "T17TLH"]

    def test_union_coverage_exceeds_each_granule(self, seam):
        acqs = group_acquisitions(seam["candidates"], seam["aoi_geojson"])
        aoi = shape(seam["aoi_geojson"])
        individual = [
            shape(c.geometry).intersection(aoi).area / aoi.area for c in seam["candidates"]
        ]
        assert max(individual) < 0.99  # neither granule alone covers the AOI
        assert acqs[0].aoi_coverage_pct > 99.0  # together they do

    def test_different_acquisitions_are_not_merged(self, seam):
        a, b = seam["candidates"]
        shifted = b.model_copy(
            update={"observed_at": b.observed_at.replace(hour=b.observed_at.hour + 3)}
        )
        acqs = group_acquisitions([a, shifted], seam["aoi_geojson"])
        assert len(acqs) == 2

    def test_processing_timestamp_does_not_split_an_acquisition(self, seam):
        """The two fixture granules have DIFFERENT processing timestamps."""
        a, b = seam["candidates"]
        assert a.item_id.split("_")[5] != b.item_id.split("_")[5]
        assert acquisition_key(a) == acquisition_key(b)

    def test_product_id_parsing(self, seam):
        item = seam["candidates"][0].item_id
        assert parse_tile_id(item) in {"T17TLG", "T17TLH"}
        assert parse_relative_orbit(item) == "R040"
        assert parse_tile_id("not-a-sentinel-id") is None


class TestMosaicking:
    def test_two_granules_produce_one_grid_sized_band(self, seam, seam_grid):
        hrefs = {c.item_id: c.assets["red"] for c in seam["candidates"]}
        band = mosaic_band(hrefs, seam_grid, categorical=False)
        assert band.values.shape == (seam_grid.height, seam_grid.width)
        assert len(band.contributors) == 2

    def test_no_seam_or_gap_at_the_tile_boundary(self, seam, seam_grid):
        """Every AOI pixel must be filled — a gap at the seam is the bug."""
        hrefs = {c.item_id: c.assets["red"] for c in seam["candidates"]}
        band = mosaic_band(hrefs, seam_grid, categorical=False)
        aoi = seam_grid.aoi_mask()
        missing = aoi & ~np.isfinite(band.values)
        assert missing.sum() == 0, f"{missing.sum()} unfilled AOI pixels at the seam"
        # Constant-valued granules: no interpolation artifact anywhere in the AOI.
        values = band.values[aoi]
        assert np.ptp(values) == pytest.approx(0.0, abs=1e-3)

    def test_single_granule_leaves_the_rest_uncovered(self, seam, seam_grid):
        """Sanity: one granule alone genuinely cannot cover the AOI."""
        north = next(c for c in seam["candidates"] if "T17TLH" in c.item_id)
        band = mosaic_band({north.item_id: north.assets["red"]}, seam_grid, categorical=False)
        aoi = seam_grid.aoi_mask()
        covered_pct = 100.0 * np.count_nonzero(band.covered & aoi) / np.count_nonzero(aoi)
        assert covered_pct < 99.0

    def test_scl_uses_nearest_neighbour(self, seam, seam_grid):
        """Categorical resampling must never invent intermediate class values."""
        fixture = build_adjacent_granules(seam["root"].parent / "cloudy", cloud_rows=(24, 34))
        grid = CanonicalGrid.from_aoi(fixture["aoi_geojson"], resolution_m=10.0)
        hrefs = {c.item_id: c.assets["scl"] for c in fixture["candidates"]}
        band = mosaic_band(hrefs, grid, categorical=True)
        present = np.unique(band.values[np.isfinite(band.values)])
        assert set(present.tolist()) <= {4.0, 9.0}, (
            f"nearest-neighbour resampling produced invented classes: {present}"
        )

    def test_overlap_resolution_is_deterministic(self, seam, seam_grid):
        hrefs = {c.item_id: c.assets["red"] for c in seam["candidates"]}
        first = mosaic_band(hrefs, seam_grid, categorical=False)
        second = mosaic_band(dict(reversed(list(hrefs.items()))), seam_grid, categorical=False)
        np.testing.assert_array_equal(
            np.nan_to_num(first.values, nan=-1), np.nan_to_num(second.values, nan=-1)
        )


class TestIdenticalAnalyticalFootprint:
    def test_two_acquisitions_with_different_source_extents_share_one_grid(self, tmp_path):
        """THE regression test for the shipped defect.

        Acquisition A is backed by both granules; acquisition B by a single
        granule that covers the AOI. Their outputs must be identical in CRS,
        size, transform and AOI pixel count.
        """
        both = build_adjacent_granules(tmp_path / "a")
        grid = CanonicalGrid.from_aoi(both["aoi_geojson"], resolution_m=10.0)
        acq_a = group_acquisitions(both["candidates"], both["aoi_geojson"])[0]

        result_a = process_acquisition(acq_a, grid, CONFIG, tmp_path / "out_a", sign=IDENTITY)
        assert result_a.usable, result_a.unusable_reason

        # A second acquisition over the same AOI on the same grid.
        other = build_adjacent_granules(tmp_path / "b", north_ndvi=0.3, south_ndvi=0.3)
        acq_b = group_acquisitions(other["candidates"], other["aoi_geojson"])[0]
        result_b = process_acquisition(acq_b, grid, CONFIG, tmp_path / "out_b", sign=IDENTITY)
        assert result_b.usable, result_b.unusable_reason

        for attr in ("crs", "width", "height", "transform", "resolution"):
            assert getattr(result_a.raster, attr) == getattr(result_b.raster, attr), attr
        assert result_a.stats.aoi_pixel_count == result_b.stats.aoi_pixel_count
        assert result_a.coverage.aoi_pixel_count == result_b.coverage.aoi_pixel_count

        # And the COGs themselves agree on the ground they cover.
        with (
            rasterio.open(result_a.outputs.ndvi_cog) as a,
            rasterio.open(result_b.outputs.ndvi_cog) as b,
        ):
            assert a.crs == b.crs
            assert (a.width, a.height) == (b.width, b.height)
            assert a.transform == b.transform
            assert a.bounds == b.bounds

    def test_statistics_use_the_full_aoi_footprint(self, seam, seam_grid, tmp_path):
        acq = group_acquisitions(seam["candidates"], seam["aoi_geojson"])[0]
        result = process_acquisition(acq, seam_grid, CONFIG, tmp_path / "out", sign=IDENTITY)
        assert result.usable
        assert result.stats.aoi_pixel_count == seam_grid.aoi_pixel_count()
        # Fixture NDVI is a constant 0.5 across BOTH granules.
        assert result.stats.ndvi_mean == pytest.approx(0.5, abs=1e-3)
        assert result.stats.ndvi_min == pytest.approx(0.5, abs=1e-3)
        assert result.stats.ndvi_max == pytest.approx(0.5, abs=1e-3)

    def test_masking_changes_valid_pixels_not_geometry(self, tmp_path):
        clear = build_adjacent_granules(tmp_path / "clear")
        cloudy = build_adjacent_granules(tmp_path / "cloudy", cloud_rows=(20, 30))
        grid = CanonicalGrid.from_aoi(clear["aoi_geojson"], resolution_m=10.0)

        r_clear = process_acquisition(
            group_acquisitions(clear["candidates"], clear["aoi_geojson"])[0],
            grid,
            CONFIG,
            tmp_path / "o1",
            sign=IDENTITY,
        )
        r_cloudy = process_acquisition(
            group_acquisitions(cloudy["candidates"], cloudy["aoi_geojson"])[0],
            grid,
            CONFIG,
            tmp_path / "o2",
            sign=IDENTITY,
        )
        assert r_clear.usable and r_cloudy.usable
        assert r_clear.raster.width == r_cloudy.raster.width
        assert r_clear.raster.height == r_cloudy.raster.height
        assert r_clear.stats.aoi_pixel_count == r_cloudy.stats.aoi_pixel_count
        # Geometry identical, valid subset smaller.
        assert r_cloudy.stats.valid_pixel_count < r_clear.stats.valid_pixel_count
        assert r_cloudy.coverage.cloud_masked_pixel_count > 0


class TestCoverageRejection:
    def test_partial_coverage_acquisition_is_rejected(self, seam, seam_grid, tmp_path):
        """A single-granule acquisition over a seam AOI must NOT be usable."""
        north = next(c for c in seam["candidates"] if "T17TLH" in c.item_id)
        acq = group_acquisitions([north], seam["aoi_geojson"])[0]
        result = process_acquisition(acq, seam_grid, CONFIG, tmp_path / "out", sign=IDENTITY)
        assert not result.usable
        assert result.unusable_reason == UNUSABLE_INSUFFICIENT_COVERAGE
        assert result.coverage.aoi_coverage_pct < 99.0
        assert result.coverage.uncovered_pixel_count > 0

    def test_coverage_threshold_is_configurable(self, seam, seam_grid, tmp_path):
        north = next(c for c in seam["candidates"] if "T17TLH" in c.item_id)
        acq = group_acquisitions([north], seam["aoi_geojson"])[0]
        permissive = ProcessingConfig(min_aoi_coverage_pct=10.0, preview_max_dim=256)
        result = process_acquisition(acq, seam_grid, permissive, tmp_path / "out", sign=IDENTITY)
        assert result.usable  # accepted only because the threshold was lowered

    def test_selection_excludes_low_coverage_acquisitions(self, seam):
        from datetime import UTC, datetime

        north = next(c for c in seam["candidates"] if "T17TLH" in c.item_id)
        acqs = group_acquisitions([north], seam["aoi_geojson"])
        selection = select_acquisitions(
            acqs,
            scene_limit=6,
            max_cloud_cover_pct=100.0,
            min_aoi_coverage_pct=99.0,
            range_start=datetime(2024, 1, 1, tzinfo=UTC),
            range_end=datetime(2024, 12, 31, tzinfo=UTC),
        )
        assert selection.selected == []
        assert selection.excluded[0].reason == REASON_COVERAGE

    def test_coverage_categories_are_exhaustive(self, seam, seam_grid, tmp_path):
        fixture = build_adjacent_granules(tmp_path / "mixed", cloud_rows=(22, 28))
        grid = CanonicalGrid.from_aoi(fixture["aoi_geojson"], resolution_m=10.0)
        acq = group_acquisitions(fixture["candidates"], fixture["aoi_geojson"])[0]
        result = process_acquisition(acq, grid, CONFIG, tmp_path / "out", sign=IDENTITY)
        c = result.coverage
        total = (
            c.uncovered_pixel_count
            + c.nodata_pixel_count
            + c.cloud_masked_pixel_count
            + c.snow_masked_pixel_count
            + c.other_masked_pixel_count
            + c.invalid_spectral_pixel_count
            + result.stats.valid_pixel_count
        )
        assert total == c.aoi_pixel_count


class TestPreviewsAndProvenance:
    def test_previews_have_identical_dimensions_across_dates(self, tmp_path):
        a = build_adjacent_granules(tmp_path / "a")
        b = build_adjacent_granules(tmp_path / "b", north_ndvi=0.2, south_ndvi=0.2)
        grid = CanonicalGrid.from_aoi(a["aoi_geojson"], resolution_m=10.0)
        results = [
            process_acquisition(
                group_acquisitions(f["candidates"], f["aoi_geojson"])[0],
                grid,
                CONFIG,
                tmp_path / f"out{i}",
                sign=IDENTITY,
            )
            for i, f in enumerate((a, b))
        ]
        sizes = set()
        for r in results:
            assert r.usable
            for png in (r.outputs.ndvi_preview, r.outputs.true_color_preview):
                if png:
                    with Image.open(png) as img:
                        sizes.add(img.size)
        assert len(sizes) == 1, f"previews differ in size: {sizes}"

    def test_nodata_is_visually_distinct_from_low_ndvi(self, seam, seam_grid, tmp_path):
        """Uncovered AOI pixels render opaque grey, not a colormap color."""
        from earth_observation.previews import NODATA_RGBA, write_ndvi_preview

        ndvi = np.full((seam_grid.height, seam_grid.width), 0.5, dtype=np.float32)
        aoi = seam_grid.aoi_mask()
        covered = np.ones_like(aoi)
        covered[: seam_grid.height // 2, :] = False  # top half unobserved
        path = tmp_path / "p.png"
        write_ndvi_preview(
            path,
            ndvi,
            display_min=-0.2,
            display_max=0.9,
            max_dim=4096,
            aoi_mask=aoi,
            covered_mask=covered,
        )
        with Image.open(path) as img:
            arr = np.asarray(img)
        missing = aoi & ~covered
        assert (arr[..., 3][missing] == 255).all()  # opaque, not transparent
        assert (arr[..., :3][missing] == np.array(NODATA_RGBA[:3])).all()

    def test_summary_records_every_contributing_granule(self, seam, seam_grid, tmp_path):
        acq = group_acquisitions(seam["candidates"], seam["aoi_geojson"])[0]
        result = process_acquisition(acq, seam_grid, CONFIG, tmp_path / "out", sign=IDENTITY)
        doc = json.loads(open(result.outputs.scene_summary).read())
        assert len(doc["contributing_item_ids"]) == 2
        assert sorted(doc["tile_ids"]) == ["T17TLG", "T17TLH"]
        assert doc["granule_count"] == 2
        assert doc["canonical_grid"]["signature"] == seam_grid.signature()
        assert set(doc["source_assets_unsigned"]) == set(acq.item_ids)
        assert doc["coverage"]["aoi_coverage_pct"] > 99.0

    def test_provenance_lists_all_contributing_items(self, seam, seam_grid, tmp_path):
        from datetime import UTC, datetime

        from earth_observation.provenance import build_provenance

        acq = group_acquisitions(seam["candidates"], seam["aoi_geojson"])[0]
        result = process_acquisition(acq, seam_grid, CONFIG, tmp_path / "out", sign=IDENTITY)
        selection = select_acquisitions(
            [acq],
            scene_limit=6,
            max_cloud_cover_pct=100.0,
            min_aoi_coverage_pct=99.0,
            range_start=datetime(2024, 1, 1, tzinfo=UTC),
            range_end=datetime(2024, 12, 31, tzinfo=UTC),
        )
        doc = build_provenance(
            analysis_id="6f1f5c62-9d94-4a2f-8f0a-2f5d2a9b1c33",
            created_at="2024-07-01T00:00:00+00:00",
            config=CONFIG,
            grid=seam_grid,
            aoi_geometry=seam["aoi_geojson"],
            aoi_area_km2=4.0,
            start_date="2024-06-01",
            end_date="2024-07-31",
            max_cloud_cover_pct=20.0,
            scene_limit=6,
            selection=selection,
            results=[result],
            outputs=[],
            software={"processing_version": "2.0.0"},
            timing={"duration_seconds": 1.0},
        )
        scene = doc["scenes"][0]
        assert sorted(scene["contributing_item_ids"]) == sorted(acq.item_ids)
        assert sorted(scene["tile_ids"]) == ["T17TLG", "T17TLH"]
        assert scene["granule_count"] == 2
        assert doc["canonical_grid"]["signature"] == seam_grid.signature()
        assert doc["processing"]["mosaic_method"] == "first-valid-by-item-id"
        assert doc["processing"]["resampling_categorical"] == "nearest"
        assert doc["processing"]["resampling_spectral"] == "bilinear"
        assert doc["scene_selection"]["min_aoi_coverage_pct"] == CONFIG.min_aoi_coverage_pct
