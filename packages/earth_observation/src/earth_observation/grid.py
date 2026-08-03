"""Canonical analysis grid.

Every analysis derives exactly ONE grid from its area of interest, and every
observation in that analysis is reprojected onto it. This is what makes
observations comparable: identical CRS, resolution, transform, width, height,
bounds, and AOI mask for every date, regardless of which Sentinel-2 granules
happened to supply the pixels.

Before this existed, each scene was clipped against its own granule extent, so
an AOI straddling a tile boundary produced rasters of different sizes covering
different ground — and statistics computed over different geographic regions
(see docs/adr/0007-canonical-analysis-grid.md).

Processing CRS
--------------
The grid uses the UTM zone containing the AOI centroid (WGS84 datum). UTM is
the native CRS of Sentinel-2 L2A assets, so for a small AOI the common case is
a same-zone reprojection that is close to a no-op; it is metric (so a fixed
10 m resolution is meaningful), conformal, and has low distortion within a
zone. The AOI is always preserved in EPSG:4326 for the API and provenance.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import numpy.typing as npt
from affine import Affine
from pyproj import CRS, Transformer
from rasterio.features import geometry_mask
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

from earth_observation.errors import UserInputError

#: Bumped whenever the grid derivation changes in a way that alters pixel
#: alignment, so provenance documents remain interpretable.
GRID_SCHEMA_VERSION = "1.0.0"

#: Sentinel-2 native resolution of the red and NIR bands used for NDVI.
DEFAULT_RESOLUTION_M = 10.0


def utm_epsg_for(lon: float, lat: float) -> int:
    """EPSG code of the WGS84 UTM zone containing a point."""
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise UserInputError(f"Coordinate out of range: ({lon}, {lat})")
    zone = int(math.floor((lon + 180.0) / 6.0) % 60) + 1
    return (32600 if lat >= 0 else 32700) + zone


class CanonicalGrid:
    """The single analytical grid shared by every observation in an analysis.

    Construct with :meth:`from_aoi`. Instances are immutable in practice and
    fully described by :meth:`to_dict`, which is what gets persisted and
    embedded in provenance.
    """

    __slots__ = (
        "aoi_geometry_4326",
        "bounds_geographic",
        "bounds_projected",
        "crs",
        "epsg",
        "height",
        "resolution",
        "schema_version",
        "transform",
        "width",
    )

    def __init__(
        self,
        *,
        epsg: int,
        transform: Affine,
        width: int,
        height: int,
        resolution: tuple[float, float],
        bounds_projected: tuple[float, float, float, float],
        bounds_geographic: tuple[float, float, float, float],
        aoi_geometry_4326: dict[str, Any],
        schema_version: str = GRID_SCHEMA_VERSION,
    ) -> None:
        self.epsg = epsg
        self.crs = f"EPSG:{epsg}"
        self.transform = transform
        self.width = width
        self.height = height
        self.resolution = resolution
        self.bounds_projected = bounds_projected
        self.bounds_geographic = bounds_geographic
        self.aoi_geometry_4326 = aoi_geometry_4326
        self.schema_version = schema_version

    # -- construction --------------------------------------------------------

    @classmethod
    def from_aoi(
        cls,
        aoi_geojson: dict[str, Any],
        *,
        resolution_m: float = DEFAULT_RESOLUTION_M,
        epsg: int | None = None,
    ) -> CanonicalGrid:
        """Derive the canonical grid from a WGS84 AOI geometry.

        The AOI is projected into the target UTM zone and its bounds are
        snapped OUTWARD to whole multiples of the resolution. Snapping to the
        CRS origin (rather than to the AOI corner) makes the pixel grid depend
        only on the CRS and resolution, so two analyses over overlapping areas
        produce co-registered pixels.
        """
        if resolution_m <= 0:
            raise UserInputError("Grid resolution must be positive")
        aoi = shape(aoi_geojson)
        if aoi.is_empty:
            raise UserInputError("AOI geometry is empty")

        centroid = aoi.centroid
        target_epsg = epsg if epsg is not None else utm_epsg_for(centroid.x, centroid.y)

        aoi_projected = _project(aoi, 4326, target_epsg)
        minx, miny, maxx, maxy = aoi_projected.bounds

        # Snap outward to the resolution lattice anchored at the CRS origin.
        minx = math.floor(minx / resolution_m) * resolution_m
        miny = math.floor(miny / resolution_m) * resolution_m
        maxx = math.ceil(maxx / resolution_m) * resolution_m
        maxy = math.ceil(maxy / resolution_m) * resolution_m

        width = round((maxx - minx) / resolution_m)
        height = round((maxy - miny) / resolution_m)
        if width < 1 or height < 1:
            raise UserInputError("AOI is smaller than one pixel at the requested resolution")

        transform = Affine(resolution_m, 0.0, minx, 0.0, -resolution_m, maxy)
        geographic = _project(
            shape(
                {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [minx, miny],
                            [maxx, miny],
                            [maxx, maxy],
                            [minx, maxy],
                            [minx, miny],
                        ]
                    ],
                }
            ),
            target_epsg,
            4326,
        ).bounds

        return cls(
            epsg=target_epsg,
            transform=transform,
            width=width,
            height=height,
            resolution=(resolution_m, resolution_m),
            bounds_projected=(minx, miny, maxx, maxy),
            bounds_geographic=geographic,
            aoi_geometry_4326=dict(mapping(aoi)),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CanonicalGrid:
        """Rehydrate a grid from its persisted representation."""
        t = data["transform"]
        return cls(
            epsg=int(data["epsg"]),
            transform=Affine(*t[:6]),
            width=int(data["width"]),
            height=int(data["height"]),
            resolution=tuple(data["resolution"]),  # type: ignore[arg-type]
            bounds_projected=tuple(data["bounds_projected"]),  # type: ignore[arg-type]
            bounds_geographic=tuple(data["bounds_geographic"]),  # type: ignore[arg-type]
            aoi_geometry_4326=data["aoi_geometry_4326"],
            schema_version=data.get("schema_version", GRID_SCHEMA_VERSION),
        )

    # -- derived products ----------------------------------------------------

    def aoi_geometry_projected(self) -> BaseGeometry:
        """The AOI polygon in the grid CRS."""
        return _project(shape(self.aoi_geometry_4326), 4326, self.epsg)

    def aoi_mask(self) -> npt.NDArray[np.bool_]:
        """Boolean mask, True inside the AOI polygon.

        This is THE analytical footprint: every observation's statistics are
        computed over exactly these pixels, so a smaller source footprint can
        never shrink the region a date is measured over — it can only reduce
        the valid-pixel count within it.
        """
        mask: npt.NDArray[np.bool_] = geometry_mask(
            [self.aoi_geometry_projected()],
            out_shape=(self.height, self.width),
            transform=self.transform,
            invert=True,
        )
        return mask

    def aoi_pixel_count(self) -> int:
        return int(np.count_nonzero(self.aoi_mask()))

    def signature(self) -> str:
        """Compact identity string used to detect grid mismatches downstream."""
        a = self.transform
        return (
            f"{self.crs}:{self.width}x{self.height}:"
            f"{a.a:.6g},{a.b:.6g},{a.c:.6g},{a.d:.6g},{a.e:.6g},{a.f:.6g}"
        )

    def matches(self, other: CanonicalGrid) -> bool:
        return self.signature() == other.signature()

    # -- serialization -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "crs": self.crs,
            "epsg": self.epsg,
            "resolution": list(self.resolution),
            "transform": [
                self.transform.a,
                self.transform.b,
                self.transform.c,
                self.transform.d,
                self.transform.e,
                self.transform.f,
            ],
            "width": self.width,
            "height": self.height,
            "bounds_projected": list(self.bounds_projected),
            "bounds_geographic": list(self.bounds_geographic),
            "aoi_geometry_4326": self.aoi_geometry_4326,
            "signature": self.signature(),
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<CanonicalGrid {self.signature()}>"


def _project(geom: BaseGeometry, from_epsg: int, to_epsg: int) -> BaseGeometry:
    if from_epsg == to_epsg:
        return geom
    transformer = Transformer.from_crs(
        CRS.from_epsg(from_epsg), CRS.from_epsg(to_epsg), always_xy=True
    )
    return shapely_transform(transformer.transform, geom)
