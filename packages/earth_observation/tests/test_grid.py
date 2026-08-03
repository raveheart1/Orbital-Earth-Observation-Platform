"""Canonical grid derivation tests."""

from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import box, mapping

from earth_observation.errors import UserInputError
from earth_observation.grid import (
    GRID_SCHEMA_VERSION,
    CanonicalGrid,
    utm_epsg_for,
)

DETROIT = dict(mapping(box(-83.15, 42.30, -83.00, 42.40)))


class TestUtmSelection:
    def test_michigan_is_zone_17n(self):
        assert utm_epsg_for(-83.1, 42.35) == 32617

    def test_zone_boundaries(self):
        assert utm_epsg_for(-179.9, 10.0) == 32601
        assert utm_epsg_for(179.9, 10.0) == 32660

    def test_southern_hemisphere_uses_327xx(self):
        assert utm_epsg_for(-58.4, -34.6) == 32721

    def test_out_of_range_rejected(self):
        with pytest.raises(UserInputError):
            utm_epsg_for(-500.0, 0.0)


class TestGridDerivation:
    def test_detroit_grid_shape(self):
        grid = CanonicalGrid.from_aoi(DETROIT, resolution_m=10.0)
        assert grid.crs == "EPSG:32617"
        assert grid.resolution == (10.0, 10.0)
        # 0.15 deg lon at 42.3N is ~12.3 km; 0.1 deg lat is ~11.1 km.
        assert 1150 < grid.width < 1350
        assert 1050 < grid.height < 1250
        assert grid.schema_version == GRID_SCHEMA_VERSION

    def test_bounds_snapped_to_resolution_lattice(self):
        grid = CanonicalGrid.from_aoi(DETROIT, resolution_m=10.0)
        minx, miny, maxx, maxy = grid.bounds_projected
        for value in (minx, miny, maxx, maxy):
            assert value % 10.0 == pytest.approx(0.0, abs=1e-6)

    def test_grid_covers_the_whole_aoi(self):
        grid = CanonicalGrid.from_aoi(DETROIT)
        aoi = grid.aoi_geometry_projected()
        minx, miny, maxx, maxy = grid.bounds_projected
        assert minx <= aoi.bounds[0] and aoi.bounds[2] <= maxx
        assert miny <= aoi.bounds[1] and aoi.bounds[3] <= maxy

    def test_transform_matches_bounds_and_size(self):
        grid = CanonicalGrid.from_aoi(DETROIT)
        a = grid.transform
        assert a.c == grid.bounds_projected[0]
        assert a.f == grid.bounds_projected[3]
        assert a.a == 10.0
        assert a.e == -10.0
        assert grid.bounds_projected[2] == pytest.approx(a.c + grid.width * 10.0)
        assert grid.bounds_projected[1] == pytest.approx(a.f - grid.height * 10.0)

    def test_derivation_is_deterministic(self):
        first = CanonicalGrid.from_aoi(DETROIT)
        second = CanonicalGrid.from_aoi(DETROIT)
        assert first.signature() == second.signature()

    def test_grids_of_overlapping_aois_are_co_registered(self):
        """Pixel corners must land on the same lattice regardless of AOI."""
        a = CanonicalGrid.from_aoi(dict(mapping(box(-83.15, 42.30, -83.00, 42.40))))
        b = CanonicalGrid.from_aoi(dict(mapping(box(-83.10, 42.32, -83.02, 42.38))))
        assert (b.transform.c - a.transform.c) % 10.0 == pytest.approx(0.0, abs=1e-6)
        assert (b.transform.f - a.transform.f) % 10.0 == pytest.approx(0.0, abs=1e-6)

    def test_roundtrip_serialization(self):
        grid = CanonicalGrid.from_aoi(DETROIT)
        restored = CanonicalGrid.from_dict(grid.to_dict())
        assert restored.signature() == grid.signature()
        assert restored.matches(grid)
        assert restored.aoi_pixel_count() == grid.aoi_pixel_count()

    def test_sub_pixel_aoi_still_yields_a_valid_grid(self):
        """Outward snapping guarantees at least one whole pixel.

        Rejecting tiny areas is the API's job (``min_aoi_area_km2``); the grid
        must never produce a zero-sized raster for a valid polygon.
        """
        tiny = dict(mapping(box(-83.0, 42.0, -83.0 + 1e-8, 42.0 + 1e-8)))
        grid = CanonicalGrid.from_aoi(tiny, resolution_m=10.0)
        assert grid.width >= 1
        assert grid.height >= 1

    def test_empty_geometry_rejected(self):
        with pytest.raises(UserInputError):
            CanonicalGrid.from_aoi({"type": "Polygon", "coordinates": []})

    def test_invalid_resolution_rejected(self):
        with pytest.raises(UserInputError):
            CanonicalGrid.from_aoi(DETROIT, resolution_m=0.0)


class TestAoiMask:
    def test_mask_shape_matches_grid(self):
        grid = CanonicalGrid.from_aoi(DETROIT)
        mask = grid.aoi_mask()
        assert mask.shape == (grid.height, grid.width)
        assert mask.dtype == np.bool_

    def test_mask_is_mostly_full_for_a_rectangular_aoi(self):
        """A lat/lon rectangle is a near-rectangle in UTM; most pixels are in."""
        grid = CanonicalGrid.from_aoi(DETROIT)
        fraction = grid.aoi_pixel_count() / (grid.width * grid.height)
        assert fraction > 0.95

    def test_mask_is_stable_across_calls(self):
        grid = CanonicalGrid.from_aoi(DETROIT)
        np.testing.assert_array_equal(grid.aoi_mask(), grid.aoi_mask())


class TestSignature:
    def test_differing_size_changes_signature(self):
        a = CanonicalGrid.from_aoi(DETROIT, resolution_m=10.0)
        b = CanonicalGrid.from_aoi(DETROIT, resolution_m=20.0)
        assert a.signature() != b.signature()
        assert not a.matches(b)

    def test_signature_includes_crs_and_shape(self):
        grid = CanonicalGrid.from_aoi(DETROIT)
        assert grid.crs in grid.signature()
        assert f"{grid.width}x{grid.height}" in grid.signature()
