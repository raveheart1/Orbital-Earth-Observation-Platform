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


# ---------------------------------------------------------------------------
# Adjacent-granule fixtures
#
# These reproduce the defect class that shipped to production: an AOI that
# straddles the boundary between two Sentinel-2 tiles. Each granule covers only
# part of the AOI, so processing either one alone yields a truncated raster and
# statistics over the wrong ground. Correct processing mosaics both.
# ---------------------------------------------------------------------------

#: The two synthetic granules split the scene vertically with a small overlap,
#: mirroring the real tile overlap. NORTH covers rows 0..24, SOUTH rows 20..40.
NORTH_ROWS = (0, 25)
SOUTH_ROWS = (20, SIZE)
#: AOI spanning the seam: rows 10..30, cols 10..30 (needs BOTH granules).
SEAM_AOI_ROWS = (10, 30)
SEAM_AOI_COLS = (10, 30)


def _granule_dir(root: Path, name: str) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_adjacent_granules(
    root: Path,
    *,
    north_ndvi: float = 0.5,
    south_ndvi: float = 0.5,
    cloud_rows: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Two adjacent granules of ONE acquisition, each covering part of the AOI.

    Reflectance uses baseline >= 04.00 encoding (``DN * 1e-4 - 0.1``). Both
    granules carry a constant NDVI over their own extent so a seam or a
    dropped granule is immediately visible in the statistics.

    ``cloud_rows`` optionally marks SCL class 9 (high-probability cloud) over a
    row range of the SOUTH granule, in 10 m grid rows.

    Returns the two candidates plus the seam-spanning AOI.
    """

    def dn_for(ndvi: float) -> tuple[int, int]:
        # NDVI = (nir - red) / (nir + red) with red fixed at reflectance 0.1.
        red_refl = 0.1
        nir_refl = red_refl * (1.0 + ndvi) / (1.0 - ndvi)
        return (round((red_refl + 0.1) * 10000), round((nir_refl + 0.1) * 10000))

    candidates: list[SceneCandidate] = []
    for name, (r0, r1), ndvi in (
        ("north", NORTH_ROWS, north_ndvi),
        ("south", SOUTH_ROWS, south_ndvi),
    ):
        rows = r1 - r0
        red_dn_val, nir_dn_val = dn_for(ndvi)
        red = np.full((rows, SIZE), red_dn_val, dtype=np.uint16)
        nir = np.full((rows, SIZE), nir_dn_val, dtype=np.uint16)
        scl = np.full((rows // 2, SIZE // 2), 4, dtype=np.uint8)
        if cloud_rows and name == "south":
            c0 = max((cloud_rows[0] - r0) // 2, 0)
            c1 = max((cloud_rows[1] - r0) // 2, 0)
            scl[c0:c1, :] = 9

        origin_y = ORIGIN_Y - r0 * RES
        gdir = _granule_dir(root, name)
        write_raster(
            gdir / "red.tif",
            red,
            transform=from_origin(ORIGIN_X, origin_y, RES, RES),
            nodata=NODATA_DN,
        )
        write_raster(
            gdir / "nir.tif",
            nir,
            transform=from_origin(ORIGIN_X, origin_y, RES, RES),
            nodata=NODATA_DN,
        )
        write_raster(
            gdir / "scl.tif",
            scl,
            transform=from_origin(ORIGIN_X, origin_y, RES * 2, RES * 2),
            nodata=0,
        )
        write_raster(
            gdir / "visual.tif",
            np.full((3, rows, SIZE), 128, dtype=np.uint8),
            transform=from_origin(ORIGIN_X, origin_y, RES, RES),
        )

        transformer = Transformer.from_crs(UTM17, "EPSG:4326", always_xy=True)
        footprint = shapely_transform(
            transformer.transform,
            box(ORIGIN_X, origin_y - rows * RES, ORIGIN_X + SIZE * RES, origin_y),
        )
        tile = "T17TLH" if name == "north" else "T17TLG"
        candidates.append(
            SceneCandidate(
                item_id=(
                    "S2A_MSIL2A_20240701T163000_R040_"
                    f"{tile}_20240701T2{'0' if name == 'north' else '1'}0000"
                ),
                collection="sentinel-2-l2a",
                observed_at=datetime(2024, 7, 1, 16, 30, tzinfo=UTC),
                cloud_cover_pct=5.0,
                geometry=dict(mapping(footprint)),
                bbox=footprint.bounds,
                epsg=32617,
                platform="sentinel-2a",
                instruments=["msi"],
                processing_baseline="05.00",
                assets={
                    "red": str(gdir / "red.tif"),
                    "nir": str(gdir / "nir.tif"),
                    "scl": str(gdir / "scl.tif"),
                    "visual": str(gdir / "visual.tif"),
                },
            )
        )

    aoi = utm_box_to_wgs84_geojson(
        ORIGIN_X + SEAM_AOI_COLS[0] * RES,
        ORIGIN_Y - SEAM_AOI_ROWS[1] * RES,
        ORIGIN_X + SEAM_AOI_COLS[1] * RES,
        ORIGIN_Y - SEAM_AOI_ROWS[0] * RES,
    )
    return {"candidates": candidates, "aoi_geojson": aoi, "root": root}
