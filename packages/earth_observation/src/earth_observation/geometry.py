"""Geometry validation and geodesic area calculation for areas of interest.

All AOIs enter the system as WGS84 (EPSG:4326) bounding boxes or polygons.
Validation is strict: malformed, antimeridian-crossing, or oversized inputs
are rejected with :class:`~earth_observation.errors.UserInputError` before any
remote request is made.
"""

from __future__ import annotations

import math
from typing import Any

from pyproj import Geod
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity

from earth_observation.errors import UserInputError

_GEOD = Geod(ellps="WGS84")

BBox = tuple[float, float, float, float]


def validate_bbox(bbox: tuple[float, ...] | list[float]) -> BBox:
    """Validate a WGS84 bounding box ``(min_lon, min_lat, max_lon, max_lat)``.

    Rejects non-finite values, out-of-range coordinates, degenerate boxes, and
    antimeridian-crossing boxes (min_lon must be strictly less than max_lon).
    Antimeridian-crossing AOIs are out of scope for this Michigan-focused
    platform and are rejected rather than silently mishandled.
    """
    if len(bbox) != 4:
        raise UserInputError(f"Bounding box must have 4 values, got {len(bbox)}")
    values = tuple(float(v) for v in bbox)
    if not all(math.isfinite(v) for v in values):
        raise UserInputError("Bounding box contains non-finite values")
    min_lon, min_lat, max_lon, max_lat = values
    if not (-180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0):
        raise UserInputError("Longitudes must be within [-180, 180]")
    if not (-90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0):
        raise UserInputError("Latitudes must be within [-90, 90]")
    if min_lon >= max_lon:
        raise UserInputError(
            "min_lon must be strictly less than max_lon "
            "(antimeridian-crossing boxes are not supported)"
        )
    if min_lat >= max_lat:
        raise UserInputError("min_lat must be strictly less than max_lat")
    return (min_lon, min_lat, max_lon, max_lat)


def bbox_polygon(bbox: BBox) -> BaseGeometry:
    """Shapely polygon for a validated bbox."""
    return box(*validate_bbox(bbox))


def geometry_from_geojson(geojson: dict[str, Any]) -> BaseGeometry:
    """Parse and validate a GeoJSON geometry (Polygon or MultiPolygon)."""
    try:
        geom = shape(geojson)
    except (ValueError, AttributeError, KeyError, TypeError) as exc:
        raise UserInputError(f"Unparseable GeoJSON geometry: {exc}") from exc
    if geom.is_empty:
        raise UserInputError("Geometry is empty")
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise UserInputError(f"Geometry must be Polygon or MultiPolygon, got {geom.geom_type}")
    if not geom.is_valid:
        raise UserInputError(f"Invalid geometry: {explain_validity(geom)}")
    min_lon, min_lat, max_lon, max_lat = geom.bounds
    validate_bbox((min_lon, min_lat, max_lon, max_lat))
    return geom


def geodesic_area_km2(geom: BaseGeometry) -> float:
    """Geodesic area of a WGS84 geometry in km², computed on the WGS84 ellipsoid.

    Using :meth:`pyproj.Geod.geometry_area_perimeter` avoids the distortion a
    fixed projected CRS would introduce and works for any AOI location.
    """
    area_m2, _ = _GEOD.geometry_area_perimeter(geom)
    return abs(area_m2) / 1.0e6


def intersection_pct(aoi: BaseGeometry, footprint: BaseGeometry) -> float:
    """Percent of the AOI's geodesic area covered by ``footprint``. 0 if disjoint."""
    if not aoi.intersects(footprint):
        return 0.0
    inter = aoi.intersection(footprint)
    if inter.is_empty:
        return 0.0
    aoi_area = geodesic_area_km2(aoi)
    if aoi_area == 0.0:
        return 0.0
    return 100.0 * geodesic_area_km2(inter) / aoi_area
