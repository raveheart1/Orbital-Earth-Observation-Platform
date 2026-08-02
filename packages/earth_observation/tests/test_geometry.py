"""Geometry validation and geodesic area tests."""

from __future__ import annotations

import pytest
from shapely.geometry import box, mapping

from earth_observation.errors import UserInputError
from earth_observation.geometry import (
    bbox_polygon,
    geodesic_area_km2,
    geometry_from_geojson,
    intersection_pct,
    validate_bbox,
)


class TestBboxValidation:
    def test_valid_michigan_bbox(self):
        assert validate_bbox((-83.3, 42.55, -83.15, 42.65)) == (-83.3, 42.55, -83.15, 42.65)

    def test_antimeridian_crossing_rejected(self):
        with pytest.raises(UserInputError, match="antimeridian"):
            validate_bbox((170.0, 40.0, -170.0, 45.0))

    @pytest.mark.parametrize(
        "bad",
        [
            (-200.0, 42.0, -83.0, 43.0),
            (-83.0, -95.0, -82.0, 43.0),
            (-83.0, 43.0, -84.0, 44.0),
            (-83.0, 43.0, -82.0, 42.0),
            (-83.0, 42.0, -83.0, 43.0),
        ],
    )
    def test_malformed_rejected(self, bad):
        with pytest.raises(UserInputError):
            validate_bbox(bad)

    def test_nan_rejected(self):
        with pytest.raises(UserInputError, match="non-finite"):
            validate_bbox((float("nan"), 42.0, -83.0, 43.0))

    def test_wrong_length_rejected(self):
        with pytest.raises(UserInputError, match="4 values"):
            validate_bbox((1.0, 2.0, 3.0))


class TestGeoJson:
    def test_valid_polygon(self):
        geom = geometry_from_geojson(mapping(box(-83.3, 42.5, -83.1, 42.7)))
        assert geom.geom_type == "Polygon"

    def test_point_rejected(self):
        with pytest.raises(UserInputError, match="Polygon"):
            geometry_from_geojson({"type": "Point", "coordinates": [-83.0, 42.0]})

    def test_self_intersecting_rejected(self):
        bowtie = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
        }
        with pytest.raises(UserInputError, match="Invalid geometry"):
            geometry_from_geojson(bowtie)

    def test_garbage_rejected(self):
        with pytest.raises(UserInputError):
            geometry_from_geojson({"type": "Polygon"})


class TestArea:
    def test_geodesic_area_michigan_scale(self):
        """0.1 deg x 0.1 deg near 42.5N is ~91 km^2 (cos-latitude shrinkage)."""
        area = geodesic_area_km2(box(-83.3, 42.5, -83.2, 42.6))
        assert 88.0 < area < 95.0

    def test_area_uses_ellipsoid_not_planar(self):
        """Same degree box at high latitude must be much smaller."""
        low = geodesic_area_km2(box(-83.3, 0.0, -83.2, 0.1))
        high = geodesic_area_km2(box(-83.3, 65.0, -83.2, 65.1))
        assert high < low * 0.6

    def test_intersection_pct(self):
        aoi = box(0.0, 0.0, 1.0, 1.0)
        half = box(0.0, 0.0, 0.5, 1.0)
        assert intersection_pct(aoi, half) == pytest.approx(50.0, abs=1.0)
        assert intersection_pct(aoi, box(5.0, 5.0, 6.0, 6.0)) == 0.0
        assert intersection_pct(aoi, aoi) == pytest.approx(100.0, abs=0.01)

    def test_bbox_polygon_roundtrip(self):
        poly = bbox_polygon((-83.3, 42.55, -83.15, 42.65))
        assert poly.bounds == (-83.3, 42.55, -83.15, 42.65)
