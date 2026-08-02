"""Public testing utilities: tiny synthetic Sentinel-2-like scenes.

Used by this package's own test suite, the top-level integration tests, and
available to downstream users who want analytically known rasters. Nothing
here is imported by production code paths.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import Affine, from_origin
from shapely.geometry import box, mapping
from shapely.ops import transform as shapely_transform

from earth_observation.types import SceneCandidate

UTM17 = "EPSG:32617"
#: Synthetic scene grid: 40x40 pixels, 10 m resolution, in UTM zone 17N.
ORIGIN_X, ORIGIN_Y = 300_000.0, 4_700_000.0
RES = 10.0
SIZE = 40
NODATA_DN = 65_535


def write_raster(
    path: Path,
    data: np.ndarray,
    *,
    transform: Affine | None = None,
    crs: str = UTM17,
    nodata: float | None = None,
) -> Path:
    """Write a (count, H, W) or (H, W) array as a GeoTIFF."""
    if data.ndim == 2:
        data = data[np.newaxis, :, :]
    transform = transform or from_origin(ORIGIN_X, ORIGIN_Y, RES, RES)
    profile = {
        "driver": "GTiff",
        "height": data.shape[1],
        "width": data.shape[2],
        "count": data.shape[0],
        "dtype": data.dtype.name,
        "crs": crs,
        "transform": transform,
    }
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)
    return path


def utm_box_to_wgs84_geojson(minx: float, miny: float, maxx: float, maxy: float) -> dict[str, Any]:
    """AOI helper: UTM17 box -> WGS84 GeoJSON polygon (as the API would submit)."""
    transformer = Transformer.from_crs(UTM17, "EPSG:4326", always_xy=True)
    return dict(mapping(shapely_transform(transformer.transform, box(minx, miny, maxx, maxy))))


def make_file_candidate(
    scene_dir: Path,
    *,
    item_id: str = "S2_TEST_SCENE",
    processing_baseline: str = "05.00",
    with_visual: bool = True,
) -> SceneCandidate:
    """Candidate whose asset hrefs are local file paths written by fixtures."""
    transformer = Transformer.from_crs(UTM17, "EPSG:4326", always_xy=True)
    footprint = shapely_transform(
        transformer.transform,
        box(ORIGIN_X, ORIGIN_Y - SIZE * RES, ORIGIN_X + SIZE * RES, ORIGIN_Y),
    )
    assets = {
        "red": str(scene_dir / "red.tif"),
        "nir": str(scene_dir / "nir.tif"),
        "scl": str(scene_dir / "scl.tif"),
    }
    if with_visual:
        assets["visual"] = str(scene_dir / "visual.tif")
    return SceneCandidate(
        item_id=item_id,
        collection="sentinel-2-l2a",
        observed_at=datetime(2024, 7, 1, 16, 30, tzinfo=UTC),
        cloud_cover_pct=5.0,
        geometry=dict(mapping(footprint)),
        bbox=footprint.bounds,
        epsg=32617,
        platform="sentinel-2a",
        instruments=["msi"],
        processing_baseline=processing_baseline,
        assets=assets,
    )


SELECTION_RANGE_START = datetime(2024, 5, 1, tzinfo=UTC)
SELECTION_RANGE_END = datetime(2024, 9, 1, tzinfo=UTC)


def make_metadata_candidate(
    item_id: str, days: int, cloud: float, overlap: float = 100.0
) -> SceneCandidate:
    """Lightweight candidate (no raster files) for selection-algorithm tests."""
    return SceneCandidate(
        item_id=item_id,
        collection="sentinel-2-l2a",
        observed_at=SELECTION_RANGE_START + timedelta(days=days),
        cloud_cover_pct=cloud,
        geometry={
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        },
        bbox=(0.0, 0.0, 1.0, 1.0),
        epsg=32617,
        platform="sentinel-2a",
        instruments=["msi"],
        processing_baseline="05.00",
        assets={"red": "r", "nir": "n", "scl": "s"},
        aoi_overlap_pct=overlap,
    )


def build_synthetic_scene(scene_dir: Path) -> dict[str, Any]:
    """A complete synthetic scene with known NDVI structure.

    Reflectance encoding uses baseline >= 04.00 semantics:
    ``reflectance = DN * 1e-4 - 0.1`` (i.e. DN = (refl + 0.1) * 10000).

    Layout on the 40x40 grid (10 m pixels):
      - Background: red refl 0.1 (DN 2000), NIR refl 0.3 (DN 4000) -> NDVI 0.5
      - Rows 14-17, cols 14-17 (in-AOI): red/NIR swapped -> NDVI -0.5
      - Rows 20-21, cols 20-23 (in-AOI): SCL=9; under-cloud NDVI bait ~0.9
      - Rows 24-25, cols 24-25 (in-AOI): red nodata (DN 65535)
      - Row 26, cols 26-27 (in-AOI): both bands refl 0.0 (DN 1000) -> zero denominator
    AOI: UTM box rows 10..30, cols 10..30 (200 m x 200 m, 400 pixels).
    """
    scene_dir.mkdir(parents=True, exist_ok=True)

    red_dn = np.full((SIZE, SIZE), 2000, dtype=np.uint16)
    nir_dn = np.full((SIZE, SIZE), 4000, dtype=np.uint16)
    scl = np.full((SIZE // 2, SIZE // 2), 4, dtype=np.uint8)  # 20 m grid: vegetation

    red_dn[14:18, 14:18] = 4000
    nir_dn[14:18, 14:18] = 2000

    scl[10, 10:12] = 9
    nir_dn[20:22, 20:24] = 20000

    red_dn[24:26, 24:26] = NODATA_DN

    red_dn[26, 26:28] = 1000
    nir_dn[26, 26:28] = 1000

    write_raster(scene_dir / "red.tif", red_dn, nodata=NODATA_DN)
    write_raster(scene_dir / "nir.tif", nir_dn, nodata=NODATA_DN)
    write_raster(
        scene_dir / "scl.tif",
        scl,
        transform=from_origin(ORIGIN_X, ORIGIN_Y, RES * 2, RES * 2),
        nodata=0,
    )
    visual = np.random.default_rng(42).integers(30, 220, size=(3, SIZE, SIZE), dtype=np.uint8)
    write_raster(scene_dir / "visual.tif", visual.astype(np.uint8))

    aoi_geojson = utm_box_to_wgs84_geojson(
        ORIGIN_X + 10 * RES,
        ORIGIN_Y - 30 * RES,
        ORIGIN_X + 30 * RES,
        ORIGIN_Y - 10 * RES,
    )
    return {
        "dir": scene_dir,
        "candidate": make_file_candidate(scene_dir),
        "aoi_geojson": aoi_geojson,
    }
